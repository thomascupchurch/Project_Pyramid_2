# Allow LAN Access for Sign Estimation App (Admin One‑Pager)

Purpose: Enable coworkers to reach a local internal web app running on a user’s Windows PC over the LAN. The app listens on TCP port 8050 (default) and uses HTTP inside the internal network only.

Why this is needed: Windows Defender Firewall blocks inbound traffic by default. A single inbound allow rule (Domain/Private profiles only) is required.

Scope & Safety:
- Profiles: Domain, Private (not Public)
- Protocol: TCP
- Port: 8050 (configurable)
- Optional restrictions: bind to specific program path and/or corporate subnets
- Reversible: a single rule that can be removed later

## Option A – Local rule (single machine)
Run PowerShell as Administrator:

```powershell
# Basic rule (Domain + Private profiles)
New-NetFirewallRule -DisplayName "SignEstimator Inbound" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8050 `
  -Profile Domain,Private
```

Optional: restrict to the app’s interpreter/exe:
```powershell
New-NetFirewallRule -DisplayName "SignEstimator Inbound" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8050 `
  -Program "C:\\Users\\<USER>\\AppData\\Local\\SignEstimator\\venv\\Scripts\\python.exe" `
  -Profile Domain,Private
```

Optional: restrict remote subnets:
```powershell
New-NetFirewallRule -DisplayName "SignEstimator Inbound" `
  -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8050 `
  -RemoteAddress 10.0.0.0/8,192.168.0.0/16 `
  -Profile Domain,Private
```

Command Prompt (Admin) alternative:
```cmd
netsh advfirewall firewall add rule name="SignEstimator Inbound" dir=in action=allow protocol=TCP localport=8050 profile=Domain,Private
```

Verification:
```powershell
Get-NetFirewallRule -DisplayName "SignEstimator Inbound" | Get-NetFirewallPortFilter | Format-Table -AutoSize
```

Removal:
```powershell
Get-NetFirewallRule -DisplayName "SignEstimator Inbound" | Remove-NetFirewallRule
```

## Option B – Central (Group Policy)
- Path: Computer Configuration > Policies > Windows Settings > Security Settings > Windows Defender Firewall with Advanced Security > Inbound Rules
- Create Rule:
  - Name: SignEstimator Inbound
  - Direction: Inbound
  - Action: Allow
  - Protocol: TCP, Local Port: 8050
  - Profiles: Domain, Private
  - Optional: Programs and Services → This program path: (python.exe or bundled exe)
  - Optional: Scope → Remote IP address: your corporate subnets

## Notes
- Users can still run locally without LAN access (127.0.0.1); this rule only enables coworkers to reach the app at http://<host-ip>:8050.
- The project also has a helper script (`scripts/ensure_firewall_rule.ps1`) which checks/creates the rule when run elevated.
