import base64, struct

def dv(d, p):
    r, s = 0, 0
    while p < len(d):
        b = d[p]; r |= (b & 0x7F) << s; p += 1
        if not (b & 0x80): break
        s += 7
    return r, p

def df(d):
    fs, p = [], 0
    while p < len(d):
        try: t, p = dv(d, p)
        except: break
        fn, wt = t >> 3, t & 7
        if wt == 0: v, p = dv(d, p); fs.append((fn, 0, v))
        elif wt == 2: l, p = dv(d, p); fs.append((fn, 2, d[p:p+l])); p += l
        elif wt == 5: fs.append((fn, 5, struct.unpack_from("<f", d, p)[0])); p += 4
        elif wt == 1: fs.append((fn, 1, struct.unpack_from("<d", d, p)[0])); p += 8
        else: break
    return fs

def ts(d):
    try:
        t = d.decode("utf-8")
        if all(c.isprintable() for c in t): return t
    except: pass
    return None

def deep(d, indent=0):
    fs = df(d)
    for fn, wt, v in fs:
        pfx = "  " * indent
        if wt == 2:
            s = ts(v)
            if s:
                print(f"{pfx}F{fn}(str)='{s}'")
            else:
                print(f"{pfx}F{fn}(bytes)[{len(v)}]:")
                deep(v, indent + 1)
        elif wt == 0:
            print(f"{pfx}F{fn}(varint)={v}")
        elif wt == 5:
            print(f"{pfx}F{fn}(float)={v}")

def extract_cmd(b64):
    raw = base64.b64decode(b64)
    top = df(raw)
    for fn, wt, v in top:
        if fn == 2 and wt == 2:
            inner = df(v)
            for ifn, iwt, iv in inner:
                if ifn == 4 and iwt == 2:
                    cmd = df(iv)
                    for cfn, cwt, cv in cmd:
                        if cwt == 2:
                            sub = df(cv)
                            for sfn, swt, sv in sub:
                                if swt == 2:
                                    entry = df(sv)
                                    sid = bus = val_bool = val_uint = val_str = None
                                    for efn, ewt, ev in entry:
                                        if efn == 1 and ewt == 0: sid = ev
                                        elif efn == 2 and ewt == 0: bus = ev
                                        elif efn == 3 and ewt == 0: val_uint = ev
                                        elif efn == 4 and ewt == 2:
                                            s = ts(ev)
                                            if s: val_str = s
                                        elif efn == 5 and ewt == 0: val_bool = bool(ev)
                                    return sid, bus, val_bool, val_uint, val_str
    return None, None, None, None, None

BN = {1:"can0",3:"lin1",8:"lin2",11:"alarm",12:"step",15:"awning",16:"ext_light",
      19:"dimmer",21:"roof_vent",22:"fresh_water",24:"screen",25:"inverter",
      34:"heat_ctrl",37:"fridge",43:"wifi",44:"bluetooth",45:"scu",49:"truma",
      58:"heater",99:"can2"}

SN = {
    (3,1):"main_switch",(3,3):"charger_active",
    (11,1):"light_living_ceiling",(12,1):"light_living_ambient",
    (15,1):"light_bedroom_ambient",(16,1):"light_nightlight",
    (19,1):"light_bathroom_ceiling",(21,1):"light_kitchen",
    (24,1):"light_outside",(43,1):"light_seating_overhead",
    (44,1):"light_bedroom_overhead",(34,1):"heat_switch_1",
    (37,1):"fridge_mode",(58,5):"heater_fan_speed",(58,4):"heater_fuel_type",
}

# All command payloads from all 3 captures (excluding subscriptions)
all_cmds = [
    # Capture 1 (193416)
    ("Eh8I/7smEgd2MC4zMi4wGMvyys4GIgoSCAoGCAMQAygB", "cap1"),
    ("Eh8Ig8E2Egd2MC4zMi4wGM/yys4GIgoSCAoGCAMQAygA", "cap1"),
    ("Eh8ImYUZEgd2MC4zMi4wGN3yys4GIgoSCAoGCAEQECgB", "cap1"),
    ("Eh8Iy6YOEgd2MC4zMi4wGOTyys4GIgoSCAoGCAEQECgA", "cap1"),
    ("Ei4I3NUKEgd2MC4zMi4wGOzyys4GIhkSFwoJCAUQOiIDRUNPCgoIBBA6IgRCb3Ro", "cap1"),
    ("Ei4ItNcNEgd2MC4zMi4wGO/yys4GIhkSFwoJCAUQOiIDT0ZGCgoIBBA6IgRCb3Ro", "cap1"),
    ("Eh8IjJ0IEgd2MC4zMi4wGIvzys4GIgoSCAoGCAEQIigB", "cap1"),
    ("Eh8I7t0yEgd2MC4zMi4wGI/zys4GIgoSCAoGCAEQIigA", "cap1"),
    # Capture 2 (193925)
    ("Eh8Ive4uEgd2MC4zMi4wGIH1ys4GIgoSCAoGCAEQEygB", "cap2"),
    ("Eh8Ii+YYEgd2MC4zMi4wGIb1ys4GIgoSCAoGCAEQEygA", "cap2"),
    ("Eh8I14UPEgd2MC4zMi4wGIj1ys4GIgoSCAoGCAEQECgB", "cap2"),
    ("Eh8I4qAhEgd2MC4zMi4wGIz1ys4GIgoSCAoGCAEQECgA", "cap2"),
    ("Eh8IubQeEgd2MC4zMi4wGI31ys4GIgoSCAoGCAEQDygB", "cap2"),
    ("Eh8I0c4MEgd2MC4zMi4wGJD1ys4GIgoSCAoGCAEQDygA", "cap2"),
    ("Eh8I3ps8Egd2MC4zMi4wGJP1ys4GIgoSCAoGCAEQLCgB", "cap2"),
    ("Eh8ItJ83Egd2MC4zMi4wGJb1ys4GIgoSCAoGCAEQLCgA", "cap2"),
    ("Eh8Ipus8Egd2MC4zMi4wGKT1ys4GIgoSCAoGCAIQGBhT", "cap2"),
    ("Eh8IxbU8Egd2MC4zMi4wGKb1ys4GIgoSCAoGCAEQCygB", "cap2"),
    ("Eh8Ir4orEgd2MC4zMi4wGKn1ys4GIgoSCAoGCAIQGBhK", "cap2"),
    ("Eh8IwNo0Egd2MC4zMi4wGKr1ys4GIgoSCAoGCAMQGBgh", "cap2"),
    ("Eh8I1J0cEgd2MC4zMi4wGKr1ys4GIgoSCAoGCAMQGBhW", "cap2"),
    ("Eh8I/a4jEgd2MC4zMi4wGK31ys4GIgoSCAoGCAEQCygA", "cap2"),
    ("Eh8IopU2Egd2MC4zMi4wGK31ys4GIgoSCAoGCAIQGBgX", "cap2"),
    ("Eh8Iq7oGEgd2MC4zMi4wGLD1ys4GIgoSCAoGCAEQDCgB", "cap2"),
    ("Eh8I2+AIEgd2MC4zMi4wGLH1ys4GIgoSCAoGCAIQGBgH", "cap2"),
    ("Eh8I65cOEgd2MC4zMi4wGLP1ys4GIgoSCAoGCAMQGBgR", "cap2"),
    ("Eh8IpKUiEgd2MC4zMi4wGLT1ys4GIgoSCAoGCAEQDCgA", "cap2"),
    ("Eh8Ih8QuEgd2MC4zMi4wGLj1ys4GIgoSCAoGCAEQFSgB", "cap2"),
    ("Eh8IjIsmEgd2MC4zMi4wGLv1ys4GIgoSCAoGCAIQFRgj", "cap2"),
    ("Eh8I2doQEgd2MC4zMi4wGL71ys4GIgoSCAoGCAEQFSgA", "cap2"),
    ("Eh8Im60ZEgd2MC4zMi4wGMD1ys4GIgoSCAoGCAEQKygB", "cap2"),
    ("Eh8IifwREgd2MC4zMi4wGML1ys4GIgoSCAoGCAIQKxgp", "cap2"),
    ("Eh8Iu/4cEgd2MC4zMi4wGMb1ys4GIgoSCAoGCAEQKygA", "cap2"),
    ("Eh8IhMwLEgd2MC4zMi4wGOT1ys4GIgoSCAoGCAEQDCgB", "cap2"),
    ("Eh8I5d4iEgd2MC4zMi4wGO31ys4GIgoSCAoGCAIQDBg2", "cap2"),
    ("Eh8IuLIlEgd2MC4zMi4wGO31ys4GIgoSCAoGCAIQDBhM", "cap2"),
    ("Eh8IlJ4bEgd2MC4zMi4wGO71ys4GIgoSCAoGCAMQDBg/", "cap2"),
    ("Eh8I8ZotEgd2MC4zMi4wGO/1ys4GIgoSCAoGCAMQDBhd", "cap2"),
    ("Eh8I4IoeEgd2MC4zMi4wGPL1ys4GIgoSCAoGCAEQDCgA", "cap2"),
    # Capture 3 (202758)
    ("Eh8I39EqEgd2MC4zMi4wGO6Ly84GIgoSCAoGCAEQCygB", "cap3"),
    ("Eh8I8JkgEgd2MC4zMi4wGPKLy84GIgoSCAoGCAEQCygA", "cap3"),
    ("Eh8IkdopEgd2MC4zMi4wGPSLy84GIgoSCAoGCAEQDCgB", "cap3"),
    ("Eh8It7UvEgd2MC4zMi4wGPiLy84GIgoSCAoGCAEQDCgA", "cap3"),
    ("Eh8In6clEgd2MC4zMi4wGP6Ly84GIgoSCAoGCAEQFSgB", "cap3"),
    ("Eh8Ik74zEgd2MC4zMi4wGIOMy84GIgoSCAoGCAEQFSgA", "cap3"),
    ("Eh8I3NEIEgd2MC4zMi4wGIaMy84GIgoSCAoGCAEQKygB", "cap3"),
    ("Eh8I3tMwEgd2MC4zMi4wGIqMy84GIgoSCAoGCAEQKygA", "cap3"),
    ("Eh8IucgCEgd2MC4zMi4wGI6My84GIgoSCAoGCAEQDygB", "cap3"),
    ("Eh8I4fQuEgd2MC4zMi4wGJGMy84GIgoSCAoGCAEQDygA", "cap3"),
    ("Eh8ImvYNEgd2MC4zMi4wGJOMy84GIgoSCAoGCAEQECgB", "cap3"),
    ("Eh8Ih7IFEgd2MC4zMi4wGJeMy84GIgoSCAoGCAEQECgA", "cap3"),
    ("Eh8Ir8gIEgd2MC4zMi4wGJmMy84GIgoSCAoGCAEQEygB", "cap3"),
    ("Eh8I/ccoEgd2MC4zMi4wGJyMy84GIgoSCAoGCAEQEygA", "cap3"),
    ("Eh8I8NwTEgd2MC4zMi4wGKCMy84GIgoSCAoGCAEQLCgB", "cap3"),
    ("Eh8IxrIMEgd2MC4zMi4wGKSMy84GIgoSCAoGCAEQLCgA", "cap3"),
]

print(f"{'SRC':<5} {'BUS':>4} {'SID':>4} {'BOOL':>6} {'UINT':>6} {'STR':<10} DECODED")
print("-" * 80)
for b64, src in all_cmds:
    sid, bus, vb, vu, vs = extract_cmd(b64)
    bn = BN.get(bus, f"?{bus}")
    vals = []
    if vb is not None: vals.append(f"bool={vb}")
    if vu is not None: vals.append(f"uint={vu}")
    if vs is not None: vals.append(f"str={vs}")
    # Decode meaning
    meaning = ""
    if bus == 3 and sid == 3: meaning = "charger_active"
    elif bus == 58 and sid == 5: meaning = f"heater_fan_speed={'ECO' if vs=='ECO' else 'OFF' if vs=='OFF' else vs}"
    elif bus == 58 and sid == 4: meaning = f"heater_fuel_type={vs}"
    elif sid == 1 and vb is not None: meaning = f"ON/OFF(bool={vb}) on bus {bus}({bn})"
    elif sid == 2 and vu is not None: meaning = f"brightness={vu} on bus {bus}({bn})"
    elif sid == 3 and vu is not None: meaning = f"color_temp={vu} on bus {bus}({bn})"
    else: meaning = f"bus={bus}({bn}) sid={sid}"
    vstr = " ".join(vals) if vals else "none"
    print(f"{src:<5} {bus:>4} {sid:>4} {str(vb):>6} {str(vu):>6} {str(vs):<10} {meaning}")
