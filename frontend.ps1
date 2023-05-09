$LocalIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -ne "Loopback Pseudo-Interface 1" -and $_.IPAddress -notlike "169.*" -and $_.IPAddress -notlike "172.*" }).IPAddress
docker run -it --pull always -p 3000:3000 -e NEXT_PUBLIC_API_URI=http://$LocalIP:7437 ghcr.io/jamesonrgrieve/agent-llm-frontend:main
