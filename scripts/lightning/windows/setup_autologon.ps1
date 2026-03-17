# Configure Windows autologon for MRW Lightning-PC 24/7 unattended operation.
# Run as Administrator: Right-click -> Run as administrator
# Requires: username and password for the account that runs NexStorm.
param(
    [Parameter(Mandatory=$true)]
    [string]$Username,
    [Parameter(Mandatory=$true)]
    [string]$Password
)
$ErrorActionPreference = "Stop"
$regPath = "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon"
Set-ItemProperty -Path $regPath -Name "DefaultUserName" -Value $Username
Set-ItemProperty -Path $regPath -Name "DefaultPassword" -Value $Password
Set-ItemProperty -Path $regPath -Name "AutoAdminLogon" -Value "1"
Set-ItemProperty -Path $regPath -Name "AutoLogonCount" -Value 999999 -Type DWord
Write-Host "Autologon configured for $Username. PC will log in automatically on boot."
Write-Host "To disable: Set AutoAdminLogon to 0 in the same registry path."
