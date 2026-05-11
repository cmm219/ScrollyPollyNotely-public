$text = Get-Clipboard -Raw
if ($text) {
    $s = New-Object System.Net.Sockets.TcpClient("127.0.0.1", 47210)
    $w = New-Object System.IO.StreamWriter($s.GetStream())
    $w.Write($text)
    $w.Flush()
    $s.Close()
}
