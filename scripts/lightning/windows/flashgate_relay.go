//go:build windows
// +build windows

// FlashGate IPC-1 relay for MRW lightning ingestion.
// Reads NexStorm FlashGate shared memory, outputs lightning_rt.ndjson and lightning_status.json.
// Auto-discovers NXFGIPC_SHMEM_*_GATE0 or SIPC_{*} (Section objects under \Sessions\*\BaseNamedObjects).
// Build: GOOS=windows GOARCH=amd64 go build -o flashgate_relay.exe
// Run on Lightning-PC with NexStorm.
package main

import (
	"bufio"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"flag"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"

	"golang.org/x/sys/windows"
)

const (
	FILE_MAP_READ    = 0x0004
	SHMEM_SIZE       = 1024
	POLL_MS          = 15
	DEFAULT_SHMEM    = ""
	DEFAULT_READER   = "Reader Semaphore"
	DEFAULT_WRITER   = "Writer Semaphore"
	SENSOR_ID        = "MRW"
	WAIT_OBJECT_0    = 0
	WAIT_TIMEOUT     = 0x00000102
	SEMAPHORE_MODIFY = 0x0002
	SYNCHRONIZE      = 0x00100000

	OBJ_CASE_INSENSITIVE = 0x40
	DIRECTORY_QUERY      = 0x0001
	STATUS_SUCCESS       = 0x0
	STATUS_NO_MORE_ENTRIES = 0x8000001A
)

var (
	kernel32            = windows.NewLazySystemDLL("kernel32")
	ntdll               = windows.NewLazySystemDLL("ntdll")
	procOpenFileMapping = kernel32.NewProc("OpenFileMappingW")
	procMapViewOfFile   = kernel32.NewProc("MapViewOfFile")
	procUnmapViewOfFile = kernel32.NewProc("UnmapViewOfFile")
	procCloseHandle    = kernel32.NewProc("CloseHandle")
	procOpenSemaphore  = kernel32.NewProc("OpenSemaphoreW")
	procWaitForSingle  = kernel32.NewProc("WaitForSingleObject")
	procReleaseSem     = kernel32.NewProc("ReleaseSemaphore")

	procNtOpenDirectoryObject   = ntdll.NewProc("NtOpenDirectoryObject")
	procNtQueryDirectoryObject = ntdll.NewProc("NtQueryDirectoryObject")
)

type unicodeString struct {
	Length        uint16
	MaximumLength uint16
	Buffer        *uint16
}

type objectAttributes struct {
	Length                   uint32
	RootDirectory            windows.Handle
	ObjectName               *unicodeString
	Attributes               uint32
	SecurityDescriptor       uintptr
	SecurityQualityOfService uintptr
}

type objectDirectoryInformation struct {
	Name     unicodeString
	TypeName unicodeString
}

// listSessionIDs returns session IDs from \Sessions (e.g. 0, 1, 2, 3).
func listSessionIDs() ([]string, error) {
	names, err := enumerateDirectoryNames(`\Sessions`, "", "")
	if err != nil {
		return nil, err
	}
	var ids []string
	for _, n := range names {
		if n == "" {
			continue
		}
		allNum := true
		for _, c := range n {
			if c < '0' || c > '9' {
				allNum = false
				break
			}
		}
		if allNum && len(n) <= 4 {
			ids = append(ids, n)
		}
	}
	return ids, nil
}

// enumerateDirectoryNames returns object names in dirPath (direct children only).
func enumerateDirectoryNames(dirPath, prefix, suffix string) ([]string, error) {
	pathUTF16, err := syscall.UTF16PtrFromString(dirPath)
	if err != nil {
		return nil, err
	}
	objName := &unicodeString{
		Length:        uint16(len(dirPath) * 2),
		MaximumLength: uint16((len(dirPath) + 1) * 2),
		Buffer:        pathUTF16,
	}
	oa := objectAttributes{
		Length:     uint32(unsafe.Sizeof(objectAttributes{})),
		Attributes: OBJ_CASE_INSENSITIVE,
		ObjectName: objName,
	}

	var hDir windows.Handle
	r, _, _ := procNtOpenDirectoryObject.Call(
		uintptr(unsafe.Pointer(&hDir)),
		uintptr(DIRECTORY_QUERY),
		uintptr(unsafe.Pointer(&oa)),
	)
	if r != STATUS_SUCCESS {
		return nil, fmt.Errorf("NtOpenDirectoryObject failed: 0x%X", r)
	}
	defer procCloseHandle.Call(uintptr(hDir))

	var names []string
	buf := make([]byte, 64*1024)
	var context uint32
	entrySize := int(unsafe.Sizeof(objectDirectoryInformation{}))

	for {
		var returnLen uint32
		r, _, _ := procNtQueryDirectoryObject.Call(
			uintptr(hDir),
			uintptr(unsafe.Pointer(&buf[0])),
			uintptr(len(buf)),
			0,
			0,
			uintptr(unsafe.Pointer(&context)),
			uintptr(unsafe.Pointer(&returnLen)),
		)
		if r == STATUS_NO_MORE_ENTRIES {
			break
		}
		if r != STATUS_SUCCESS {
			break
		}

		for offset := 0; offset+entrySize <= len(buf); offset += entrySize {
			info := (*objectDirectoryInformation)(unsafe.Pointer(&buf[offset]))
			if info.Name.Length == 0 {
				break
			}
			if info.Name.Buffer == nil {
				continue
			}
			sl := (*[4096]uint16)(unsafe.Pointer(info.Name.Buffer))[:info.Name.Length/2]
			name := syscall.UTF16ToString(sl)
			match := (prefix == "" && suffix == "") || (strings.HasPrefix(name, prefix) && strings.HasSuffix(name, suffix))
			if match {
				names = append(names, name)
			}
		}
		if context == 0 {
			break
		}
	}

	return names, nil
}

// listDiagnosticObjects enumerates BaseNamedObjects and all Sessions\N\BaseNamedObjects,
// returning objects whose names contain any of the keywords (case-insensitive).
func listDiagnosticObjects(keywords []string) {
	dirs := []string{`\BaseNamedObjects`}
	sessionIDs, err := listSessionIDs()
	if err == nil {
		for _, sid := range sessionIDs {
			dirs = append(dirs, fmt.Sprintf(`\Sessions\%s\BaseNamedObjects`, sid))
		}
	} else {
		dirs = append(dirs, `\Sessions\1\BaseNamedObjects`)
	}

	containsAny := func(name string) bool {
		lower := strings.ToLower(name)
		for _, kw := range keywords {
			if strings.Contains(lower, strings.ToLower(kw)) {
				return true
			}
		}
		return false
	}

	for _, dirPath := range dirs {
		names, err := enumerateDirectoryNames(dirPath, "", "")
		if err != nil {
			fmt.Fprintf(os.Stderr, "%s: %v\n", dirPath, err)
			continue
		}
		for _, name := range names {
			if containsAny(name) {
				fmt.Printf("%s\t%s\n", dirPath, name)
			}
		}
	}
}

// validateShmemContents attempts to attach to the named shared memory and validate
// the record structure (FlashGate IPC-1: comma-separated, 15 fields). Returns true if valid.
// For SIPC_*, also accepts attachable memory (format validated at relay runtime).
func validateShmemContents(name string) bool {
	hMap, err := openFileMapping(FILE_MAP_READ, name)
	if err != nil || hMap == 0 {
		return false
	}
	defer closeHandle(hMap)
	ptr, err := mapViewOfFile(hMap, FILE_MAP_READ, SHMEM_SIZE)
	if err != nil || ptr == nil {
		return false
	}
	defer unmapViewOfFile(ptr)
	buf := make([]byte, SHMEM_SIZE)
	for i := 0; i < SHMEM_SIZE; i++ {
		buf[i] = *(*byte)(unsafe.Pointer(uintptr(ptr) + uintptr(i)))
	}
	rawLine := strings.TrimRight(string(buf), "\x00")
	trimmed := strings.TrimSpace(rawLine)
	if trimmed == "" {
		return true
	}
	if _, err = parseLine(rawLine); err == nil {
		return true
	}
	// SIPC may use same format; if we can attach, accept (relay will validate at runtime)
	if strings.HasPrefix(name, "SIPC_") {
		return true
	}
	return false
}

func discoverFlashGateShmem() (string, error) {
	dirs := []string{`\BaseNamedObjects`}
	sessionIDs, err := listSessionIDs()
	if err == nil {
		for _, sid := range sessionIDs {
			dirs = append(dirs, fmt.Sprintf(`\Sessions\%s\BaseNamedObjects`, sid))
		}
	} else {
		dirs = append(dirs, `\Sessions\1\BaseNamedObjects`)
	}

	var nxfgMatches, sipcMatches []string
	for _, dirPath := range dirs {
		if m, err := enumerateDirectory(dirPath, "NXFGIPC_SHMEM_", "_GATE0"); err == nil {
			nxfgMatches = append(nxfgMatches, m...)
		}
		if m, err := enumerateDirectory(dirPath, "SIPC_", ""); err == nil {
			sipcMatches = append(sipcMatches, m...)
		}
	}

	// Prefer NXFGIPC, then SIPC. Sort each and dedupe.
	sort.Strings(nxfgMatches)
	sort.Strings(sipcMatches)
	var candidates []string
	seen := make(map[string]bool)
	for _, n := range nxfgMatches {
		if !seen[n] {
			seen[n] = true
			candidates = append(candidates, n)
		}
	}
	for _, n := range sipcMatches {
		if !seen[n] {
			seen[n] = true
			candidates = append(candidates, n)
		}
	}

	if len(candidates) == 0 {
		return "", fmt.Errorf("no FlashGate shared memory found (patterns: NXFGIPC_SHMEM_*_GATE0, SIPC_{*}). Ensure NexStorm is running. Use --shmem to override.")
	}

	for _, name := range candidates {
		if validateShmemContents(name) {
			return name, nil
		}
	}
	return "", fmt.Errorf("no valid FlashGate shared memory (tried %d candidates; record structure validation failed). Use --shmem to override.", len(candidates))
}

func enumerateDirectory(dirPath, prefix, suffix string) ([]string, error) {
	pathUTF16, err := syscall.UTF16PtrFromString(dirPath)
	if err != nil {
		return nil, err
	}
	objName := &unicodeString{
		Length:        uint16(len(dirPath) * 2),
		MaximumLength: uint16((len(dirPath) + 1) * 2),
		Buffer:        pathUTF16,
	}
	oa := objectAttributes{
		Length:     uint32(unsafe.Sizeof(objectAttributes{})),
		Attributes: OBJ_CASE_INSENSITIVE,
		ObjectName: objName,
	}

	var hDir windows.Handle
	r, _, _ := procNtOpenDirectoryObject.Call(
		uintptr(unsafe.Pointer(&hDir)),
		uintptr(DIRECTORY_QUERY),
		uintptr(unsafe.Pointer(&oa)),
	)
	if r != STATUS_SUCCESS {
		return nil, fmt.Errorf("NtOpenDirectoryObject failed: 0x%X", r)
	}
	defer procCloseHandle.Call(uintptr(hDir))

	var matches []string
	buf := make([]byte, 64*1024)
	var context uint32
	entrySize := int(unsafe.Sizeof(objectDirectoryInformation{}))

	for {
		var returnLen uint32
		r, _, _ := procNtQueryDirectoryObject.Call(
			uintptr(hDir),
			uintptr(unsafe.Pointer(&buf[0])),
			uintptr(len(buf)),
			0,
			0,
			uintptr(unsafe.Pointer(&context)),
			uintptr(unsafe.Pointer(&returnLen)),
		)
		if r == STATUS_NO_MORE_ENTRIES {
			break
		}
		if r != STATUS_SUCCESS {
			break
		}

		for offset := 0; offset+entrySize <= len(buf); offset += entrySize {
			info := (*objectDirectoryInformation)(unsafe.Pointer(&buf[offset]))
			if info.Name.Length == 0 {
				break
			}
			if info.Name.Buffer == nil {
				continue
			}
			sl := (*[4096]uint16)(unsafe.Pointer(info.Name.Buffer))[:info.Name.Length/2]
			name := syscall.UTF16ToString(sl)
			if strings.HasPrefix(name, prefix) && strings.HasSuffix(name, suffix) {
				matches = append(matches, name)
			}
		}
		if context == 0 {
			break
		}
	}

	return matches, nil
}

func openFileMapping(access uint32, name string) (windows.Handle, error) {
	n, _ := syscall.UTF16PtrFromString(name)
	h, _, err := procOpenFileMapping.Call(uintptr(access), 0, uintptr(unsafe.Pointer(n)))
	if h == 0 {
		return 0, err
	}
	return windows.Handle(h), nil
}

func mapViewOfFile(h windows.Handle, access uint32, size uintptr) (unsafe.Pointer, error) {
	p, _, err := procMapViewOfFile.Call(uintptr(h), uintptr(access), 0, 0, size)
	if p == 0 {
		return nil, err
	}
	return unsafe.Pointer(p), nil
}

func unmapViewOfFile(p unsafe.Pointer) {
	procUnmapViewOfFile.Call(uintptr(p))
}

func closeHandle(h windows.Handle) {
	procCloseHandle.Call(uintptr(h))
}

func openSemaphore(access uint32, name string) (windows.Handle, error) {
	n, _ := syscall.UTF16PtrFromString(name)
	h, _, err := procOpenSemaphore.Call(uintptr(access), 0, uintptr(unsafe.Pointer(n)))
	if h == 0 {
		return 0, err
	}
	return windows.Handle(h), nil
}

func waitForSingleObject(h windows.Handle, ms uint32) (uint32, error) {
	r, _, err := procWaitForSingle.Call(uintptr(h), uintptr(ms))
	return uint32(r), err
}

func releaseSemaphore(h windows.Handle) {
	procReleaseSem.Call(uintptr(h), 1, 0)
}

type flashgateFields struct {
	Count         int
	Year          int
	Month         int
	Day           int
	TimestampSecs int
	TracBearing   float64
	TracDistance  float64
	RawBearing    float64
	RawDistance   float64
	TracX         float64
	TracY         float64
	Correlated    int
	StrikeType    int
	StrikePol     int
}

func parseLine(line string) (*flashgateFields, error) {
	parts := strings.Split(line, ",")
	if len(parts) < 15 {
		return nil, fmt.Errorf("expected 15 fields, got %d", len(parts))
	}
	f := &flashgateFields{}
	f.Count, _ = strconv.Atoi(strings.TrimSpace(parts[0]))
	f.Year, _ = strconv.Atoi(strings.TrimSpace(parts[1]))
	f.Month, _ = strconv.Atoi(strings.TrimSpace(parts[2]))
	f.Day, _ = strconv.Atoi(strings.TrimSpace(parts[3]))
	f.TimestampSecs, _ = strconv.Atoi(strings.TrimSpace(parts[4]))
	f.TracBearing, _ = strconv.ParseFloat(strings.TrimSpace(parts[5]), 64)
	f.TracDistance, _ = strconv.ParseFloat(strings.TrimSpace(parts[6]), 64)
	f.RawBearing, _ = strconv.ParseFloat(strings.TrimSpace(parts[7]), 64)
	f.RawDistance, _ = strconv.ParseFloat(strings.TrimSpace(parts[8]), 64)
	f.TracX, _ = strconv.ParseFloat(strings.TrimSpace(parts[9]), 64)
	f.TracY, _ = strconv.ParseFloat(strings.TrimSpace(parts[10]), 64)
	f.Correlated, _ = strconv.Atoi(strings.TrimSpace(parts[11]))
	f.StrikeType, _ = strconv.Atoi(strings.TrimSpace(parts[13]))
	f.StrikePol, _ = strconv.Atoi(strings.TrimSpace(parts[14]))
	return f, nil
}

func isNoise(f *flashgateFields) bool {
	return f.TracBearing == -1 || f.TracDistance == -1 || f.RawBearing == -1 || f.RawDistance == -1
}

func isHeartbeat(f *flashgateFields) bool {
	if f.Year == -9 || f.Month == -9 || f.Day == -9 || f.Count == -9 {
		return true
	}
	if f.TracBearing == -9 || f.TracDistance == -9 || f.RawDistance == -9 {
		return true
	}
	if f.TracX == -9 || f.TracY == -9 || f.Correlated == -9 || f.StrikeType == -9 || f.StrikePol == -9 {
		return true
	}
	return false
}

func timestampToUTC(f *flashgateFields) string {
	secs := f.TimestampSecs
	if secs > 1e9 {
		return time.Unix(int64(secs), 0).UTC().Format("2006-01-02T15:04:05.000Z")
	}
	loc, _ := time.LoadLocation("America/New_York")
	if secs >= 86400 {
		secs = secs % 86400
	}
	t := time.Date(f.Year, time.Month(f.Month), f.Day, 0, 0, secs, 0, loc)
	return t.UTC().Format("2006-01-02T15:04:05.000Z")
}

func makeStrikeID(ts string, rawB, rawD float64, sensor string) string {
	key := fmt.Sprintf("%s|%v|%v|%s", ts, rawB, rawD, sensor)
	h := sha256.Sum256([]byte(key))
	return hex.EncodeToString(h[:])[:32]
}

func toCanonicalStrike(f *flashgateFields, rawLine, ingestedAt, sensorID string) map[string]interface{} {
	ts := timestampToUTC(f)
	rawB, rawD := f.RawBearing, f.RawDistance
	strikeType := "CG"
	if f.StrikeType == 1 {
		strikeType = "IC"
	}
	polarity := "positive"
	if f.StrikePol == 1 {
		polarity = "negative"
	}
	rec := map[string]interface{}{
		"strike_id":       makeStrikeID(ts, rawB, rawD, sensorID),
		"timestamp_utc":   ts,
		"sensor_id":       sensorID,
		"source":          "flashgate_ipc1",
		"source_seq":      f.Count,
		"raw_bearing_deg": nil,
		"raw_distance_km": nil,
		"trac_bearing_deg": nil,
		"trac_distance_km": nil,
		"x_raw":           f.TracX,
		"y_raw":           f.TracY,
		"is_correlated":   f.Correlated != 0,
		"strike_type":     strikeType,
		"polarity":        polarity,
		"is_noise":        isNoise(f),
		"ingested_at_utc": ingestedAt,
		"raw_payload":     strings.TrimSpace(rawLine),
	}
	if rawB >= 0 {
		rec["raw_bearing_deg"] = rawB
	}
	if rawD >= 0 {
		rec["raw_distance_km"] = rawD
	}
	if f.TracBearing >= 0 {
		rec["trac_bearing_deg"] = f.TracBearing
	}
	if f.TracDistance >= 0 {
		rec["trac_distance_km"] = f.TracDistance
	}
	return rec
}

func toHealth(running bool, heartbeatAt, lastMsgAt, lastStrikeAt *string, totalMsg, totalStrike, totalNoise, totalHeartbeat int, antennaRot *float64, lastErr *string) map[string]interface{} {
	h := map[string]interface{}{
		"relay_running":                 running,
		"source_heartbeat_seen_at_utc":  nil,
		"last_message_at_utc":           nil,
		"last_strike_at_utc":            nil,
		"total_messages":                totalMsg,
		"total_strikes":                 totalStrike,
		"total_noise":                   totalNoise,
		"total_heartbeats":              totalHeartbeat,
		"antenna_rotation_deg_last":     nil,
		"last_error":                    nil,
	}
	if heartbeatAt != nil {
		h["source_heartbeat_seen_at_utc"] = *heartbeatAt
	}
	if lastMsgAt != nil {
		h["last_message_at_utc"] = *lastMsgAt
	}
	if lastStrikeAt != nil {
		h["last_strike_at_utc"] = *lastStrikeAt
	}
	if antennaRot != nil {
		h["antenna_rotation_deg_last"] = *antennaRot
	}
	if lastErr != nil {
		h["last_error"] = *lastErr
	}
	return h
}

func runRelay(shmem, readerSem, writerSem, outputDir, sensorID string, emitNoise bool) error {
	hMap, err := openFileMapping(FILE_MAP_READ, shmem)
	if err != nil || hMap == 0 {
		return fmt.Errorf("OpenFileMapping failed: %v. Is NexStorm running? Shared memory: %s", err, shmem)
	}
	defer closeHandle(hMap)

	semPairs := [][2]string{{readerSem, writerSem}}
	if strings.HasPrefix(shmem, "SIPC_") && readerSem == DEFAULT_READER && writerSem == DEFAULT_WRITER {
		semPairs = [][2]string{{DEFAULT_READER, DEFAULT_WRITER}, {shmem + "_Reader", shmem + "_Writer"}}
	}
	var hReader, hWriter windows.Handle
	for _, pair := range semPairs {
		hReader, err = openSemaphore(SYNCHRONIZE|SEMAPHORE_MODIFY, pair[0])
		if err != nil || hReader == 0 {
			continue
		}
		hWriter, err = openSemaphore(SYNCHRONIZE|SEMAPHORE_MODIFY, pair[1])
		if err != nil || hWriter == 0 {
			closeHandle(hReader)
			continue
		}
		break
	}
	if hReader == 0 || hWriter == 0 {
		return fmt.Errorf("OpenSemaphore failed: tried Reader/Writer Semaphore and %s_Reader/_Writer", shmem)
	}
	defer closeHandle(hReader)
	defer closeHandle(hWriter)

	ptr, err := mapViewOfFile(hMap, FILE_MAP_READ, SHMEM_SIZE)
	if err != nil || ptr == nil {
		return fmt.Errorf("MapViewOfFile failed: %v", err)
	}
	defer unmapViewOfFile(ptr)

	if err := os.MkdirAll(outputDir, 0755); err != nil {
		return err
	}
	rtPath := filepath.Join(outputDir, "lightning_rt.ndjson")
	statusPath := filepath.Join(outputDir, "lightning_status.json")
	noisePath := ""
	if emitNoise {
		noisePath = filepath.Join(outputDir, "lightning_noise.ndjson")
	}

	rtFile, err := os.OpenFile(rtPath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
	if err != nil {
		return err
	}
	defer rtFile.Close()
	rtWriter := bufio.NewWriter(rtFile)

	var noiseFile *os.File
	if emitNoise {
		noiseFile, _ = os.OpenFile(noisePath, os.O_APPEND|os.O_CREATE|os.O_WRONLY, 0644)
		if noiseFile != nil {
			defer noiseFile.Close()
		}
	}

	totalMsg, totalStrike, totalNoise, totalHeartbeat := 0, 0, 0, 0
	var lastStrikeAt, lastMsgAt, heartbeatAt string
	var antennaRot float64
	var lastErr string

	writeStatus := func(running bool) {
		var hbPtr, msgPtr, strikePtr, errPtr *string
		var antPtr *float64
		if heartbeatAt != "" {
			hbPtr = &heartbeatAt
		}
		if lastMsgAt != "" {
			msgPtr = &lastMsgAt
		}
		if lastStrikeAt != "" {
			strikePtr = &lastStrikeAt
		}
		if lastErr != "" {
			errPtr = &lastErr
		}
		if totalHeartbeat > 0 {
			antPtr = &antennaRot
		}
		h := toHealth(running, hbPtr, msgPtr, strikePtr, totalMsg, totalStrike, totalNoise, totalHeartbeat, antPtr, errPtr)
		b, _ := json.MarshalIndent(h, "", "  ")
		os.WriteFile(statusPath, b, 0644)
	}

	defer func() { writeStatus(false) }()

	for {
		r, _ := waitForSingleObject(hReader, POLL_MS)
		if r == WAIT_TIMEOUT {
			writeStatus(true)
			continue
		}
		if r != WAIT_OBJECT_0 {
			lastErr = fmt.Sprintf("WaitForSingleObject returned %d", r)
			continue
		}

		totalMsg++
		ingestedAt := time.Now().UTC().Format("2006-01-02T15:04:05.000Z")
		lastMsgAt = ingestedAt

		buf := make([]byte, SHMEM_SIZE)
		for i := 0; i < SHMEM_SIZE; i++ {
			buf[i] = *(*byte)(unsafe.Pointer(uintptr(ptr) + uintptr(i)))
		}
		rawLine := strings.TrimRight(string(buf), "\x00")
		releaseSemaphore(hWriter)

		if strings.TrimSpace(rawLine) == "" {
			continue
		}

		f, err := parseLine(rawLine)
		if err != nil {
			lastErr = err.Error()
			continue
		}

		if isHeartbeat(f) {
			totalHeartbeat++
			heartbeatAt = ingestedAt
			antennaRot = f.RawBearing
			continue
		}

		if isNoise(f) {
			totalNoise++
			if emitNoise && noiseFile != nil {
				rec := toCanonicalStrike(f, rawLine, ingestedAt, sensorID)
				b, _ := json.Marshal(rec)
				noiseFile.Write(append(b, '\n'))
			}
			continue
		}

		totalStrike++
		lastStrikeAt = ingestedAt
		rec := toCanonicalStrike(f, rawLine, ingestedAt, sensorID)
		b, _ := json.Marshal(rec)
		rtWriter.Write(append(b, '\n'))
		rtWriter.Flush()
		writeStatus(true)
	}
}

func main() {
	outputDir := flag.String("output-dir", `C:\MRW\lightning`, "Output directory")
	shmem := flag.String("shmem", "", "Shared memory name (default: auto-discover NXFGIPC_SHMEM_*_GATE0 or SIPC_{*})")
	readerSem := flag.String("reader-sem", DEFAULT_READER, "Reader semaphore name")
	writerSem := flag.String("writer-sem", DEFAULT_WRITER, "Writer semaphore name")
	sensorID := flag.String("sensor-id", SENSOR_ID, "Sensor ID")
	emitNoise := flag.Bool("noise", false, "Emit lightning_noise.ndjson")
	listObjs := flag.Bool("list", false, "List named objects matching NXFG/GATE/IPC/SHMEM/NexStorm and exit (diagnostic)")
	retrySec := flag.Int("retry-sec", 600, "Retry discovery every 15s for up to N seconds (0=no retry)")
	flag.Parse()

	if *listObjs {
		listDiagnosticObjects([]string{"NXFG", "GATE", "IPC", "SHMEM", "SIPC", "NexStorm"})
		return
	}

	resolvedShmem := *shmem
	if resolvedShmem == "" {
		deadline := time.Now().Add(time.Duration(*retrySec) * time.Second)
		for {
			discovered, err := discoverFlashGateShmem()
			if err == nil {
				resolvedShmem = discovered
				fmt.Fprintf(os.Stderr, "FlashGate: attached to shared memory: %s\n", resolvedShmem)
				break
			}
			if time.Now().After(deadline) || *retrySec <= 0 {
				fmt.Fprintf(os.Stderr, "Error: %v\n", err)
				os.Exit(1)
			}
			fmt.Fprintf(os.Stderr, "FlashGate: waiting for NexStorm IPC (retry in 15s): %v\n", err)
			time.Sleep(15 * time.Second)
		}
	}

	if err := runRelay(resolvedShmem, *readerSem, *writerSem, *outputDir, *sensorID, *emitNoise); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}
