# Local-first, single-process web app bound to 127.0.0.1

The Rekordbox database can only be written safely on the machine that runs
Rekordbox, so the entire app runs as one local process on the DJ's machine,
serving a browser UI on 127.0.0.1:8787 exclusively. No cloud deployment, no
multi-user access, no native app packaging (Electron/Tauri considered and
rejected: a browser plus local server delivers the same UX without a packaging
pipeline). This removes the network and auth attack surface instead of
mitigating it. Decided at kickoff, 2026-08-16.
