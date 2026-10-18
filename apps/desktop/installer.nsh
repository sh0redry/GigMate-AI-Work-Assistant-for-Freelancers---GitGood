!macro customInstall
  ; The actual Docker reset waits until GigMate has a local Docker daemon.
  CreateDirectory "$APPDATA\GigMate"
  FileOpen $0 "$APPDATA\GigMate\reset-on-next-start" w
  FileWrite $0 "fresh-install"
  FileClose $0
!macroend
