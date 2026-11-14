property goc : "__GOC__"

-- Bật máy chủ giao diện nếu chưa chạy
on batMayChu()
	set py to quoted form of (goc & "/pyvideotrans/.venv/bin/python")
	set sv to quoted form of (goc & "/hang_doi.py")
	set lg to quoted form of (goc & "/.hang_doi.log")
	do shell script "export PATH=/opt/homebrew/bin:/usr/local/bin:$PATH; if ! curl -s -m 1 http://127.0.0.1:8765/api/ping >/dev/null; then cd " & quoted form of goc & "; nohup " & py & " " & sv & " > " & lg & " 2>&1 & for i in $(seq 1 60); do curl -s -m 1 http://127.0.0.1:8765/api/ping >/dev/null && break; sleep 0.25; done; fi"
end batMayChu

on run
	batMayChu()
	open location "http://127.0.0.1:8765"
end run

-- Kéo thả video vào icon app: đưa vào hàng chờ
on open droppedItems
	batMayChu()
	set args to ""
	repeat with f in droppedItems
		set args to args & " " & quoted form of POSIX path of f
	end repeat
	do shell script quoted form of (goc & "/pyvideotrans/.venv/bin/python") & " " & quoted form of (goc & "/hang_doi.py") & " --add-files" & args
	open location "http://127.0.0.1:8765"
end open
