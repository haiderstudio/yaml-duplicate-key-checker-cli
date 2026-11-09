```text
examples/duplicates.yaml:5: duplicate key 'name' (first on line 3: first-app; this line: second-app)
examples/duplicates.yaml:9: duplicate key 'host' (first on line 8: localhost; this line: 127.0.0.1)
examples/duplicates.yaml:11: duplicate key 'port' (first on line 10: 8080; this line: 9090)
examples/duplicates.yaml:12: duplicate key 'port' (first on line 10: 8080; this line: 9091)
examples/duplicates.yaml:14: duplicate key 'quoted' (first on line 13: one; this line: two)
examples/configs/app.yaml:3: duplicate key 'host' (first on line 2: db.example.com; this line: db-backup.example.com)
Checked 4 file(s), 6 problem(s) in 2 file(s).
```

Output of `sh examples/run-example.sh` — the checker on the whole
`examples/` folder. It exits 1, because the examples contain files
with duplicates on purpose; the script itself exits 0.
