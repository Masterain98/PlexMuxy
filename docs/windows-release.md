# Windows release acceptance

PlexMuxy publishes two Windows forms:

- portable CLI and GUI ZIP archives, with the existing NotifyIcon fallback;
- a per-user Inno Setup installer with a Start-menu shortcut, fixed `com.plexmuxy.gui` AppUserModelID, uninstaller, and registered `plexmuxy://` protocol.

Installed notifications use Windows Toast when the installed identity and protocol registration are present. Notification body/actions can only pass `plexmuxy://job/<UUID>` with `view` or `output`; the parser rejects arbitrary paths, commands, unknown query keys, and extra arguments. A Toast failure falls back to the portable notification backend and cannot fail a mux job.

Before release, validate install, upgrade, uninstall, notification-center persistence, task activation, output activation, icon/DPI behavior, WebView2 handling, long Unicode paths, cancellation, and clean-machine startup on supported Windows 10 and Windows 11 builds. Record exact OS builds and screenshots/logs in the release validation record. Code signing is conditional on repository secrets and must be verified with `Get-AuthenticodeSignature` when enabled.
