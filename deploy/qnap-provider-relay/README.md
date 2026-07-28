# QNAP provider metadata relay

This stateless Container Station application is the narrow network bridge used
when a Kodi VPN exit is rejected by a public provider. It does not receive
Real-Debrid credentials or resolved playback traffic.

Deployment constraints:

- pin `MWO_RELAY_IMAGE` by GHCR digest;
- bind production to an explicit private QNAP LAN address, never `0.0.0.0`;
- do not add volumes, secrets, host networking or elevated capabilities;
- keep the fixed provider/path allowlist in the image;
- use the isolated loopback smoke before replacing the production project.

Validate the Compose policy:

```bash
python tools/qnap_provider_relay.py policy \
  --mode production \
  --env-file deploy/qnap-provider-relay/env.example \
  --allow-placeholder
```

The host lifecycle tool uploads only this Compose file and a mode-0600
environment file. Smoke mode uses a unique directory and project; after
verification, run its matching `destroy` command to remove all containers,
networks and control files.
