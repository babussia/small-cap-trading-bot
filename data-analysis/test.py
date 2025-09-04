trade_file = "trade_logs/trade_log-2025-09-03.txt"

with open(trade_file, "r", encoding="utf-8-sig") as f:
    for line in f:
        line = line.strip()
        if not line:
            continue
        print("RAW LINE:", repr(line))
        parts = [p.strip() for p in line.split("|") if p.strip()]
        print("PARTS:", parts)
        sym = parts[0].split()[0]
        print("SYMBOL:", sym)
        tdata = {"symbol": sym}
        for part in parts[1:]:
            if "=" not in part:
                continue
            key, value = part.split("=", 1)
            key = key.strip()
            value = value.strip()
            tdata[key] = value
        print("PARSED DATA:", tdata)
