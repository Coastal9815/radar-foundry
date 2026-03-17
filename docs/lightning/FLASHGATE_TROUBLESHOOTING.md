# FlashGate Relay — Troubleshooting

## Diagnostic: flashgate_relay cannot find FlashGate shared memory

### Quick diagnostic

On Lightning-PC, run:

```powershell
C:\MRW\lightning\flashgate_relay.exe --list
```

This enumerates Windows named objects in `\BaseNamedObjects` and `\Sessions\N\BaseNamedObjects` that contain NXFG, GATE, IPC, SHMEM, or NexStorm.

### Expected vs actual (2026-03-14)

| Location | Expected | Actual on Lightning-PC |
|----------|----------|------------------------|
| `\BaseNamedObjects` | `NXFGIPC_SHMEM_*_GATE0` | (none) |
| `\Sessions\1\BaseNamedObjects` | `NXFGIPC_SHMEM_*_GATE0` | `NexStormInstance` only |
| `\Sessions\2\BaseNamedObjects` | — | `SIPC_{GUID}` (StormVue IPC) |

**Root cause:** The FlashGate shared memory object `NXFGIPC_SHMEM_*_GATE0` **does not exist**. NexStorm is running (NexStormInstance in session 1) but FlashGate IPC is not creating the shared memory.

### Session IDs

- **Session 0** — Services. Typically inaccessible to non-admin; `NtOpenDirectoryObject` may fail with 0xC0000034.
- **Session 1** — Console or primary RDP. User `scott` is in session 1 (rdp-tcp#0). NexStorm runs here.
- **Session 2+** — Additional RDP sessions. `SIPC_{GUID}` in session 2 is StormVue/NGX Data Server IPC.

The relay now searches all sessions (1, 2, 3, …) when discovering shared memory. Session 0 is attempted but may fail without admin rights.

### Object name pattern

The relay looks for:

- **Prefix:** `NXFGIPC_SHMEM_`
- **Suffix:** `_GATE0`
- **Example:** `NXFGIPC_SHMEM_0822931589443_238731_GATE0` (from NexStorm Appendix C)

NexStorm may use different instance IDs; the middle segment varies per install. No object matching this pattern was found.

### FlashGate enablement

**Where to enable:** **Options → FlashGate** (main menu). FlashGate is a toggle under the Options menu—click to enable. When disabled (default), NexStorm does not create the shared memory object. Restart NexStorm after enabling.

- **Registry:** No FlashGate-related keys found under `HKCU\SOFTWARE\Astrogenic\NexStorm\Config`.
- **Config file:** `confdata.bin` exists; format unknown.
- **FlashGate download:** `nxipc_src.zip` from Astrogenic (FlashGate IPC demo with C++ source). The shared memory is created by **NexStorm** when FlashGate IPC is active; the demo is a consumer.

### Exact fix

1. **Enable FlashGate in NexStorm**
   - Open NexStorm → Options → Configuration (or similar).
   - Look for "FlashGate", "IPC", "Advanced Gateway", or "External applications" in the manual Appendix C.
   - Enable the option and restart NexStorm.

2. **Verify shared memory appears**
   ```powershell
   C:\MRW\lightning\flashgate_relay.exe --list
   ```
   You should see `NXFGIPC_SHMEM_*_GATE0` in the output.

3. **Run the relay**
   ```powershell
   C:\MRW\lightning\flashgate_relay.exe --output-dir C:\MRW\lightning
   ```

### Manual override

If you know the exact shared memory name (e.g. from another tool or the manual):

```powershell
flashgate_relay.exe --shmem "NXFGIPC_SHMEM_0822931589443_238731_GATE0" --output-dir C:\MRW\lightning
```

### Next actions

1. **Check NexStorm Manual PDF** — Search for "FlashGate", "Appendix C", "IPC", "shared memory". Identify the exact menu path to enable it.
2. **Contact Astrogenic** — If the manual does not describe enablement, ask support: "How do I enable FlashGate IPC shared memory (NXFGIPC_SHMEM_*_GATE0) in NexStorm 1.9.6?"
3. **Fallback: tail .nex** — If FlashGate cannot be enabled, use the .nex tailing path for realtime strikes (see lightning architecture docs).
