"""Explain stated product differences without inventing measurements or ranking by MHz/MP."""
import html
import re

from app.core.search_text import fold


def camera_parts(value):
    parts = re.split(r'[;；\n]+|,\s*(?=(?:Camera\s+(?:chính|góc|tele)|\d+(?:[.,]\d+)?\s*MP\b))', value, flags=re.I)
    modules = []
    for part in (p.strip(' ,') for p in parts):
        if not part:
            continue
        if modules and not re.search(r'\d+\s*MP\b', part, re.I):
            modules[-1] += ', ' + part
        else:
            modules.append(part)
    return modules


def format_spec(key, value):
    return '\n'.join(camera_parts(value)) if key in ('camera', 'front_camera') else value


def narrative_ram(description):
    """Only an explicit RAM paragraph in the performance section, never upgrades, images or another model."""
    text = re.sub(r'<!--.*?-->|<(script|style)\b[^>]*>.*?</\1>', '', description or '', flags=re.I | re.S)
    section = re.search(r'<h2\b[^>]*>\s*Hiệu năng[^<]*</h2>(.*?)(?=<h2\b|$)', text, re.I | re.S)
    if not section:
        return None
    values = set()
    for paragraph in re.findall(r'<p\b[^>]*>(.*?)</p>', section[1], re.I | re.S):
        visible = html.unescape(re.sub('<[^>]*>', '', paragraph)).strip()
        match = re.match(r'RAM\s+(\d+)\s*GB\b', visible, re.I)
        if match:
            amounts = re.findall(r'\b(\d+)\s*GB\b', visible, re.I)
            if len(set(amounts)) != 1 or re.search(r'\b(?:tối đa|nâng cấp|có thể|hoặc)\b', visible, re.I):
                return None
            values.add(match[1])
    return f'{next(iter(values))} GB' if len(values) == 1 else None


def split_processor(specs):
    parts = specs.get('cpu', '').split(' · ')
    imaging = [p for p in parts if re.search(r'MariSilicon|Imaging NPU', p, re.I)]
    cpu = [p for p in parts if p not in imaging]
    if imaging:
        specs['imaging'] = ' · '.join(imaging)
        if cpu:
            specs['cpu'] = ' · '.join(cpu)
        else:
            specs.pop('cpu', None)


def _number(value):
    return f'{value:g}'.replace('.', ',')


def amount(specs, key, unit):
    value = specs.get(key, '')
    found = re.findall(r'(\d+(?:[.,]\d+)*)\s*' + unit + r'\b', value, re.I)
    if len(found) != 1:
        return None
    number = found[0]
    if re.fullmatch(r'\d{1,2}(?:[.,]\d{3})+', number):
        number = re.sub('[.,]', '', number)
    try:
        return float(number.replace(',', '.'))
    except ValueError:
        return None


def resolution(specs):
    m = re.search(r'\b(\d{3,4})\s*[x×]\s*(\d{3,4})\b', specs.get('screen', ''), re.I)
    return (int(m[1]), int(m[2])) if m else None


def _positive(value, pattern):
    text = fold(value)
    text = re.sub(r'khong\s+(?:co\s+|ho tro\s+)?(?:ois|chong rung quang hoc|tele\w*)', '', text)
    return bool(re.search(pattern, text))


def product_insights(specs, kind):
    lines = []
    cpu = specs.get('cpu')
    if cpu:
        chip = fold(cpu)
        # Sources and scope are documented, these are architecture descriptions, never benchmark predictions.
        if re.search(r'dimensity\s*7300(?:\b|[- ])', chip):
            detail = 'bốn nhân Cortex-A78 và bốn nhân Cortex-A55, hướng đến ứng dụng hằng ngày, đa nhiệm và game với thiết lập phù hợp'
        elif re.search(r'snapdragon\s*8\s*gen\s*1\b', chip):
            detail = 'có nhân hiệu năng Cortex-X2, phù hợp khi ưu tiên xử lý tác vụ nặng, game và chỉnh sửa ảnh'
        else:
            detail = ('xử lý biên dịch mã, tính toán và ứng dụng làm việc' if kind == 'laptop'
                      else 'đảm nhiệm mở ứng dụng, xử lý ảnh và các tác vụ hằng ngày')
        line = f'CPU: {cpu}, {detail}.'
        if specs.get('imaging'):
            line += f" Bộ xử lý hình ảnh riêng: {specs['imaging']}, hỗ trợ xử lý ảnh và video."
        lines.append(line)
    if specs.get('ram'):
        lines.append(f"RAM: {specs['ram']}, là bộ nhớ cho các ứng dụng đang mở, hữu ích khi chuyển giữa nhiều ứng dụng"
                     + (' hoặc làm việc với nhiều tab và công cụ lập trình.' if kind == 'laptop' else ' và tab trình duyệt.'))
    if specs.get('gpu'):
        lines.append(f"GPU: {specs['gpu']}, phụ trách đồ họa trong game, giao diện và tác vụ xử lý hình ảnh tương thích.")
    if specs.get('screen'):
        display = f"Màn hình: {specs['screen']}"
        if specs.get('refresh'):
            display += f", {specs['refresh']}"
        lines.append(display + ', phục vụ đọc nội dung, xem ảnh và giải trí' +
                     (', tần số quét cao giúp thao tác cuộn và chuyển động liền mạch khi ứng dụng hỗ trợ.'
                      if (amount(specs, 'refresh', 'Hz') or 0) > 60 else '.'))
    if specs.get('battery'):
        lines.append(f"Pin: {specs['battery']}. " + ('Dung lượng Wh thể hiện mức năng lượng pin có thể lưu trữ.'
                     if 'wh' in fold(specs['battery']) else 'Dung lượng mAh là một yếu tố để cân nhắc khi thường xuyên dùng máy xa nguồn sạc.'))
    if specs.get('camera'):
        camera = specs['camera']
        uses = []
        if _positive(camera, r'\bois\b|chong rung quang hoc'):
            uses.append('OIS hỗ trợ giảm ảnh hưởng của rung tay')
        if _positive(camera, r'\btele\w*|zoom quang'):
            uses.append('tele phục vụ chân dung và chủ thể ở xa')
        if re.search(r'goc (?:sieu )?rong|ultra', fold(camera)):
            uses.append('góc rộng phù hợp chụp nhóm và phong cảnh')
        uses_text = ', '.join(uses)
        lines.append('Camera sau:\n' + format_spec('camera', camera) +
                     ('\n' + uses_text[0].upper() + uses_text[1:] + '.' if uses else '\nPhục vụ ghi hình, chụp tài liệu và lưu lại khung cảnh.'))
    if specs.get('front_camera'):
        lines.append('Camera trước: ' + format_spec('front_camera', specs['front_camera']) + ', phục vụ selfie và gọi video.')
    if specs.get('storage'):
        lines.append(f"Bộ nhớ: {specs['storage']}, dành cho ứng dụng, ảnh, video và tài liệu lưu trên máy.")
    return lines[:8]


def comparison_details(products, specs, rows, comparable):
    """Return concrete differences and conditional uses, without creating a second scored winner."""
    names = [p['ProductName'] for p in products]
    if len(set(names)) != len(names):
        names = [f"{p['ProductName']} ({p['VariantName']})" for p in products]
    differences, handled = [], set()
    hints = [[] for _ in products]

    def numeric(key, label, unit, purpose, tail):
        values = [amount(s, key, unit) for s in specs]
        if not comparable or any(v is None for v in values) or len(set(values)) == 1:
            return
        high, low = max(values), min(values)
        text = '\n'.join(f'{name}: {_number(value)} {unit}' for name, value in zip(names, values))
        leaders = [i for i, v in enumerate(values) if v == high]
        differences.append(f'{label}:\n{text}\nChênh lệch cao nhất {_number(high - low)} {unit}, {tail}.')
        handled.add(key)
        for i in leaders:
            hints[i].append(f"{purpose} với {_number(high)} {unit}")

    numeric('ram', 'RAM và đa nhiệm', 'GB', 'ưu tiên mở nhiều ứng dụng',
            'RAM lớn hơn cho thêm không gian bộ nhớ khi giữ nhiều ứng dụng đang mở')
    numeric('battery', 'Dung lượng pin', 'mAh', 'ưu tiên dung lượng pin khi di chuyển',
            'đây là khác biệt về dung lượng pin, không quy đổi thành số giờ sử dụng')
    numeric('battery', 'Năng lượng pin', 'Wh', 'ưu tiên năng lượng pin',
            'đây là khác biệt về năng lượng lưu trữ trong pin')
    screens = [resolution(s) for s in specs]
    if comparable and all(screens) and len({a * b for a, b in screens}) > 1:
        pixels = [a * b for a, b in screens]
        values = '\n'.join(f'{name}: {a} × {b}' for name, (a, b) in zip(names, screens))
        differences.append(f'Màn hình và độ sắc nét:\n{values}\nĐộ phân giải cao hơn tạo nhiều điểm ảnh để thể hiện chữ và chi tiết ảnh, đồng thời tăng lượng điểm ảnh GPU phải xử lý ở độ phân giải gốc.')
        handled.add('screen')
        for i, count in enumerate(pixels):
            if count == max(pixels):
                hints[i].append('ưu tiên đọc chữ và xem chi tiết ảnh trên màn hình có độ phân giải cao hơn')
    if comparable and all('camera' in s for s in specs):
        for pattern, label in [(r'goc (?:sieu )?rong|ultra', 'Camera góc rộng'), (r'\btele\w*', 'Camera tele')]:
            modules = [next((part for part in camera_parts(s['camera']) if re.search(pattern, fold(part))), None) for s in specs]
            if all(modules) and len(set(modules)) > 1:
                purpose = 'chụp nhóm và phong cảnh' if 'rộng' in label else 'chụp chân dung và chủ thể ở xa'
                differences.append(label + ':\n' + '\n'.join(f'{name}: {part}' for name, part in zip(names, modules)) +
                                   f'\nỐng kính này phục vụ {purpose}, số MP riêng lẻ chưa xác định chất lượng ảnh thực tế.')
                handled.add('camera')
    has_technical_tradeoff = any(hints)
    prices = [float(p['Price']) for p in products]
    if len(set(prices)) > 1:
        money = lambda value: f'{int(value):,}'.replace(',', '.') + ' đ'
        differences.append('Giá bán:\n' + '\n'.join(f'{name}: {money(price)}' for name, price in zip(names, prices)) +
                           f'\nChênh lệch {money(max(prices) - min(prices))}.')
        for i, price in enumerate(prices):
            if price == min(prices) and has_technical_tradeoff:
                hints[i].append('ưu tiên tiết kiệm chi phí mua máy')
    for row in rows:
        values = row['Values']
        if row['Key'] in handled or any(v == 'Chưa có dữ liệu' for v in values):
            continue
        if len({re.sub(r'\s+', '', fold(v)) for v in values}) > 1:
            text = row['Label'] + ':\n' + '\n'.join(f'{name}: {value}' for name, value in zip(names, values))
            if row['Key'] == 'gpu':
                text += '\nGPU xử lý đồ họa và game, xung MHz giữa hai kiến trúc khác nhau không dùng để kết luận GPU nào nhanh hơn.'
            elif row['Key'] == 'imaging':
                text += '\nBộ xử lý hình ảnh đảm nhiệm ảnh và video, đây không phải CPU chạy ứng dụng.'
            differences.append(text)
    recommendation = '\n'.join(f"Chọn {name} nếu bạn {', '.join(options[:3])}." for name, options in zip(names, hints)
                               if options) if comparable else ''
    return differences[:12], recommendation
