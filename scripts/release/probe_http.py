"""ENV-003 technical pre-acceptance over a real loopback socket, synthetic only.

This does not certify independent review, an official organizer API or a UI.
Starts its own server on an ephemeral loopback port and always stops it.
"""
import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]


def request_json(base, path, body=None, media='application/json'):
    """Loopback probe, independent of proxy settings and in-process TestClient."""
    req = urllib.request.Request(base + path, data=body,
                                 headers={'Content-Type': media} if body is not None else {})
    tick = time.perf_counter()
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        response = opener.open(req, timeout=10)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        return response.code, json.loads(response.read()), (time.perf_counter() - tick) * 1000


def stop_server(process):
    if process.poll() is None:
        process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)


@contextmanager
def listening_server(python, cwd, env, extra_args=()):
    """Own one server; cleanup also covers failed readiness and failed assertions."""
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    process = subprocess.Popen([str(python), '-m', 'goodsai.api', '--host', '127.0.0.1', '--port', str(port), *extra_args],
                               cwd=cwd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        deadline = time.monotonic() + 30
        while process.poll() is None and time.monotonic() < deadline:
            try:
                status, health, _ = request_json(base, '/health')
                if status == 200 and health.get('service') == 'goodsai':
                    break
            except OSError:
                pass
            time.sleep(.1)
        else:
            raise RuntimeError('Isolated server did not become ready')
        yield base, process
    finally:
        stop_server(process)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    target = args.output.absolute()
    if target.exists() or target.resolve() != target or ROOT/'outputs' not in target.parents:
        parser.error('Use a new non-symlink path under ignored outputs/')
    from goodsai.contracts import Product, load_config, validate_prediction
    from goodsai.verify import Extractor
    config = load_config()
    core = Extractor(config)
    inputs = [
        ('phone', '761', 'Смартфон Samsung QA-901 8/256GB', 'Батарея 5100 mAh.'),
        ('kettle', '482', 'Чайник Bosch QA-902 1,7 л 2200 Вт', None),
        ('unknown_category', 'unknown', 'Неизвестный товар QA-903', None),
        ('unknown_brand', '761', 'Смартфон Zorion QA-904', None),
        ('conflict', '761', 'Смартфон Samsung QA-905', 'Оперативная память 8 ГБ. Оперативная память 12 ГБ.'),
        ('html_emoji', '482', '😀 Чайник <b>Bosch</b> QA-906', '<p>Объем 1,7 л</p><p>2200 Вт</p>'),
    ]
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    started = time.perf_counter()
    process = subprocess.Popen([sys.executable, '-m', 'goodsai.api', '--host', '127.0.0.1', '--port', str(port)],
                               cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def request(path, body=None, media='application/json'):
        return request_json(base, path, body, media)

    try:
        deadline = time.monotonic()+30
        while True:
            try:
                status, health, _ = request('/health')
                if status == 200: break
            except OSError:
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Isolated server did not become ready')
            time.sleep(.1)
        startup = time.perf_counter()-started
        checks, latencies = [], []
        for repeat in range(3):
            for name, category, title, description in inputs:
                product = Product('synthetic-'+name, category, title, description)
                status, result, ms = request('/predict', json.dumps(product.as_dict()).encode())
                expected = core.predict(product, 'http-rules-v0')
                passed = status == 200 and result == expected
                if passed: validate_prediction(result, config, product)
                checks.append({'case': name, 'repeat': repeat+1, 'passed': passed, 'http_status':status})
                latencies.append(ms)
        for name, body, media, want in [
            ('invalid_json', b'{', 'application/json', 400),
            ('wrong_media', b'{}', 'text/plain', 415),
            ('oversize', b' '*(128*1024+1), 'application/json', 413),
            ('invalid_product', b'{}', 'application/json', 422),
        ]:
            status, _, _ = request('/predict', body, media)
            checks.append({'case':name,'passed':status == want,'http_status':status})
        _, index, _ = request('/')
        _, schema, _ = request('/openapi.json')
        paths = sorted(schema['paths'])
        diagnostics = []
        for name, category, title, description, attribute, expected, issue in [
            ('battery_star', '761', 'Смартфон Samsung QA-907', 'Батарея 5100 мА*ч.', 'battery_mah', '5100', 74),
            ('color_in_brand', '482', 'Электрочайник RED SOLUTION QA-908', None, 'color', None, 15),
        ]:
            p = Product('synthetic-'+name, category, title, description)
            status, result, _ = request('/predict', json.dumps(p.as_dict()).encode())
            got = next(a['value'] for a in result['attributes'] if a['attribute'] == attribute)
            diagnostics.append({'case':name,'passed':status == 200 and got == expected,'issue':issue})
        rss = None
        status_file = Path(f'/proc/{process.pid}/status')
        if status_file.exists():
            for line in status_file.read_text().splitlines():
                if line.startswith('VmHWM:'): rss = int(line.split()[1])/1024
        report = {'scope':'author technical pre-acceptance, synthetic, loopback; not independent acceptance',
                  'candidate_sha':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
                  'mode':'rules', 'independent_reviewer':False, 'quality':'N/A_no_human_reference',
                  'transport_passed':all(c['passed'] for c in checks),'checks':checks,
                  'checks_passed':sum(c['passed'] for c in checks),'checks_total':len(checks),
                  'server_start_seconds':startup,'request_p50_ms':statistics.median(latencies),
                  'request_p95_ms':sorted(latencies)[int(.95*(len(latencies)-1))],
                  'server_peak_rss_mib':rss,'api_status':health.get('api_status'),
                  'root_is_service_json':isinstance(index,dict) and index.get('service')=='goodsai',
                  'documented_paths':paths,'semantic_regressions':diagnostics,
                  'ui_rehearsal':'BLOCKED: no review UI or persistence/export workflow in candidate',
                  'server_cleanup':'finally terminate and wait'}
    finally:
        stop_server(process)
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as stream:
        json.dump(report,stream,ensure_ascii=True,indent=2)
        stream.write('\n')
    print(json.dumps({k:report[k] for k in ('candidate_sha','checks_passed','checks_total','transport_passed','ui_rehearsal')}))
    return 0 if report['transport_passed'] else 1


if __name__ == '__main__': raise SystemExit(main())
