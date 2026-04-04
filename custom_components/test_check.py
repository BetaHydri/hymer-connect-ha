import json, asyncio, aiohttp, importlib.util, os
from urllib.parse import quote
for line in open('.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip())
spec = importlib.util.spec_from_file_location('const', 'hymer_connect/const.py')
const = importlib.util.module_from_spec(spec)
spec.loader.exec_module(const)
spec2 = importlib.util.spec_from_file_location('pia', 'hymer_connect/pia_decoder.py')
pia = importlib.util.module_from_spec(spec2)
spec2.loader.exec_module(pia)
reqs = json.load(open('logs/pia_requests.json'))
async def test():
    async with aiohttp.ClientSession() as s:
        u,p = os.environ['HYMER_USERNAME'], os.environ['HYMER_PASSWORD']
        rt = os.environ['HYMER_EHG_REFRESH_TOKEN']
        async with s.post(f'{const.API_BASE_URL}{const.ENDPOINT_AUTH}', headers={
            'Accept':'application/json','Content-Type':'application/x-www-form-urlencoded',
            'Authorization':const.OAUTH2_BASIC_AUTH,'User-Agent':const.USER_AGENT,
            const.HEADER_EHG_BRAND:f'Hymer/{const.APP_VERSION}'},
            data=f'grant_type=password&username={quote(u,safe="")}&password={quote(p,safe="")}') as r:
            at = (await r.json())['access_token']
        print('AUTH OK', flush=True)
        async with s.post(f'{const.API_BASE_URL}/api/ehg/v1/vehicles/urn:ehg:vehicle:hy-0020411878/remoteAccessToken',
            headers={'Accept':'application/json','Content-Type':'application/json','User-Agent':const.USER_AGENT,
            const.HEADER_EHG_BRAND:f'Hymer/{const.APP_VERSION}','Authorization':f'Bearer {at}'},
            json={'token':rt}) as r:
            ehg = (await r.json())['token']
        print('TOKEN OK', flush=True)
        async with s.post(f'{const.API_BASE_URL_APPCOMM}{const.SIGNALR_NEGOTIATE_PATH}?negotiateVersion=1',
            headers={'Content-Type':'text/plain;charset=UTF-8','X-Requested-With':'XMLHttpRequest','User-Agent':const.USER_AGENT},data='') as r:
            neg = await r.json()
        au,st = neg['url'],neg['accessToken']
        async with s.post(au.replace('client/?','client/negotiate?'),
            headers={'Authorization':f'Bearer {st}','Content-Type':'text/plain;charset=UTF-8','User-Agent':const.USER_AGENT},data='') as r:
            ct = (await r.json())['connectionToken']
        print('NEGOTIATE OK', flush=True)
        async with s.ws_connect(au.replace('https://','wss://')+f'&id={ct}&access_token={st}',headers={'User-Agent':const.USER_AGENT}) as ws:
            await ws.send_str('{"protocol":"json","version":1}\x1e')
            await ws.receive()
            await ws.send_str(json.dumps({'arguments':[{'accessToken':at,'ehgAccessToken':ehg,
                'vehicleUrn':'urn:ehg:vehicle:hy-0020411878','scuUrn':'urn:ehg:scu:s481.01.00.013.970'}],
                'invocationId':'0','target':'UpdateTokens','type':1})+'\x1e')
            await ws.receive(timeout=10)
            print('UPDATETOKENS OK', flush=True)
            for req in reqs:
                await ws.send_str(json.dumps({'arguments':[req],'target':'PiaRequest','type':1})+'\x1e')
            print(f'SENT {len(reqs)} REQS', flush=True)
            sensors = {}
            try:
                while True:
                    msg = await ws.receive(timeout=20)
                    if msg.type == aiohttp.WSMsgType.TEXT:
                        for p in msg.data.split('\x1e'):
                            p = p.strip()
                            if not p: continue
                            pp = json.loads(p)
                            if pp.get('type')==6:
                                await ws.send_str('{"type":6}\x1e')
                            elif pp.get('target')=='PiaResponse':
                                a=pp.get('arguments',[])
                                if a and isinstance(a[0],str):
                                    sensors.update(pia.decode_pia_payload(a[0]))
                    else: break
            except asyncio.TimeoutError: pass
            print(f'TOTAL: {len(sensors)} sensors', flush=True)
            for k in sorted(sensors.keys()):
                if any(w in k for w in ['light','fridge','heat','truma','boiler','switch_12v']):
                    print(f'  {k}: {sensors[k]}')
            print('---UNMAPPED---')
            for k in sorted(sensors.keys()):
                if k.startswith('bus'):
                    print(f'  {k}: {sensors[k]}')
asyncio.run(test())
