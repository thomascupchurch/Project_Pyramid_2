# Windows Defender Firewall: Allow Rules for Two Local Apps

Audience: IT administrators managing Windows Defender Firewall on a domain-joined workstation. Purpose: enable inbound TCP access over LAN for two internal web apps hosted on the same machine.

Summary
- Create inbound allow rules for each app's port (Domain/Private profiles). Example ports: 8050 and 8060.
- Optionally scope by program path to the app launcher or python.exe instance.
- Confirm listeners and verify rule hit using Test-NetConnection and netstat.

Details
1) Identify host and ports
   - Host: the workstation's IPv4 address on the LAN (example: 172.16.1.155).
   - App A (Estimator): TCP 8050.
   - App B (Second App): TCP 8060.

2) Create inbound allow rules (ports)
   - Open Windows Defender Firewall with Advanced Security
   - Inbound Rules → New Rule… → Port → TCP → Specific local ports: 8050 → Allow → Profiles: Domain and Private → Name: "Sign Estimation App (TCP 8050)"
   - Repeat for 8060: Name: "Sign Estimation App B (TCP 8060)"

3) Optional program scoping (advanced)
   - Instead of port-based rule, use Program rule and point to the launcher or python.exe used to run the app. This can reduce surface area but may require updates when paths change.

4) Verification
   - Ensure the apps are listening on their ports (the launcher can show this). From another LAN host:
     - Test-NetConnection 172.16.1.155 -Port 8050
     - Test-NetConnection 172.16.1.155 -Port 8060
   - Expect TcpTestSucceeded: True when rules and listeners are in place.

5) Change management
   - Rules apply only to Domain and Private profiles. Not exposed on Public. No inbound from the internet is opened by these rules alone.
   - If ports or executables change, update the rules accordingly.

Appendix: netsh alternative
- netsh advfirewall firewall add rule name="Sign Estimation App (TCP 8050)" dir=in action=allow protocol=TCP localport=8050 profile=domain,private
- netsh advfirewall firewall add rule name="Sign Estimation App B (TCP 8060)" dir=in action=allow protocol=TCP localport=8060 profile=domain,private
