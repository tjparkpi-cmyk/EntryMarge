# EntryMerge 2.0 browser core - original merge logic adapted for Pyodide
import argparse, base64, copy, io, json, os, secrets, string, tarfile
from pathlib import PurePosixPath
PROJECT_PATH = "temp/project.json"
ALPHABET = string.ascii_lowercase + string.digits
ARRAY_FIELDS = ("objects", "scenes", "variables", "messages", "functions", "tables")
UNION_FIELDS = ("expansionBlocks", "aiUtilizeBlocks", "hardwareLiteBlocks", "externalModules", "externalModulesLite")
def make_id(used):
    while True:
        value = ''.join(secrets.choice(ALPHABET) for _ in range(4))
        if value not in used:
            used.add(value)
            return value


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def safe_name(name):
    name = name.replace('\\', '/')
    p = PurePosixPath(name)
    if p.is_absolute() or '..' in p.parts:
        raise ValueError(f"안전하지 않은 압축 내부 경로: {name}")
    return str(p)


def read_ent(item):
    name, raw = item
    try:
        tf = tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz')
    except (tarfile.TarError, OSError) as e:
        raise ValueError(f"ENT 파일을 열 수 없습니다: {name} ({e})")
    project_bytes, assets = None, {}
    with tf:
        for member in tf.getmembers():
            member_name = safe_name(member.name)
            if not member.isfile():
                continue
            stream = tf.extractfile(member)
            if stream is None:
                continue
            data = stream.read()
            if member_name == PROJECT_PATH:
                project_bytes = data
            elif member_name.startswith('temp/'):
                assets[member_name] = data
    if project_bytes is None:
        raise ValueError(f"{name}에 {PROJECT_PATH}가 없습니다.")
    try:
        project = json.loads(project_bytes.decode('utf-8-sig'))
    except Exception as e:
        raise ValueError(f"{name}의 project.json 오류: {e}")
    if not isinstance(project, dict):
        raise ValueError("project.json 최상위 데이터가 객체가 아닙니다.")
    for field in ARRAY_FIELDS:
        if not isinstance(project.get(field, []), list):
            raise ValueError(f"project.json의 {field} 데이터가 리스트가 아닙니다.")
    return project, assets


def all_ids(project):
    found = set()
    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get('id'), str):
                found.add(x['id'])
            for v in x.values(): walk(v)
        elif isinstance(x, list):
            for v in x: walk(v)
    walk(project)
    # IDs nested in the script JSON string are not visible to the walk above.
    for obj in project.get('objects', []):
        try:
            tree = json.loads(obj.get('script', '[]'))
            walk(tree)
        except Exception:
            pass
    return found


def remap_tree(value, mapping):
    if isinstance(value, dict):
        return {k: remap_tree(v, mapping) for k, v in value.items()}
    if isinstance(value, list):
        return [remap_tree(v, mapping) for v in value]
    if isinstance(value, str):
        return mapping.get(value, value)
    return value


def rewrite_object(obj, mapping, block_mapping):
    item = remap_tree(obj, mapping)
    script = item.get('script')
    if isinstance(script, str):
        try:
            tree = json.loads(script)
            def blocks(node):
                if isinstance(node, dict):
                    result = {}
                    for k, v in node.items():
                        if k == 'id' and 'type' in node and isinstance(v, str):
                            result[k] = block_mapping.get(v, v)
                        else:
                            result[k] = blocks(v)
                    return result
                if isinstance(node, list): return [blocks(v) for v in node]
                if isinstance(node, str): return mapping.get(node, node)
                return node
            item['script'] = json.dumps(blocks(tree), ensure_ascii=False, separators=(',', ':'))
        except json.JSONDecodeError:
            pass
    return item


def merge_ent_files(paths, output_path, mode='objects'):
    if len(paths) < 2:
        raise ValueError("ENT 파일을 2개 이상 선택해 주세요.")
    if mode not in ('objects', 'scenes'):
        raise ValueError("병합 모드는 objects 또는 scenes여야 합니다.")
    loaded = [read_ent(p) for p in paths]
    projects = [x[0] for x in loaded]
    assets_by_project = [x[1] for x in loaded]
    result = copy.deepcopy(projects[0])
    for f in ARRAY_FIELDS:
        result[f] = copy.deepcopy(projects[0].get(f, []))
    for f in UNION_FIELDS:
        result[f] = list(copy.deepcopy(projects[0].get(f, [])))

    used = all_ids(projects[0])
    primary_scenes = projects[0].get('scenes', [])
    if not primary_scenes:
        raise ValueError("첫 번째 작품에 장면이 없습니다.")
    primary_scene_id = primary_scenes[0].get('id')

    # Keep track of original IDs and records already included in the result.
    scene_records = {s.get('id'): canon(s) for s in result['scenes'] if isinstance(s, dict)}
    object_records = {o.get('id'): canon(o) for o in result['objects'] if isinstance(o, dict)}
    variable_records = list(result['variables'])
    other_records = {f: list(result.get(f, [])) for f in ('messages', 'functions', 'tables')}

    merged_assets = dict(assets_by_project[0])
    asset_maps = [{p: p for p in assets_by_project[0]}]

    for pi in range(1, len(projects)):
        src = copy.deepcopy(projects[pi])
        mapping = {}

        # Asset names: identical files are shared; different files with the same
        # path receive a new filename, and matching project.json references move.
        amap = {}
        for old_path, data in assets_by_project[pi].items():
            dest = old_path
            if dest in merged_assets and merged_assets[dest] != data:
                p = PurePosixPath(dest)
                while True:
                    candidate = str(p.with_name(f"{p.stem}_{make_id(used)}{p.suffix}"))
                    if candidate not in merged_assets:
                        dest = candidate
                        break
            amap[old_path] = dest
            merged_assets.setdefault(dest, data)
        mapping.update(amap)
        asset_maps.append(amap)

        # Scene mapping. A = all objects go into the first scene. B = preserve
        # distinct scenes, deduplicating only identical scenes with same IDs.
        smap = {}
        for scene in src.get('scenes', []):
            old = scene.get('id')
            if not isinstance(old, str):
                continue
            if mode == 'objects':
                smap[old] = primary_scene_id
            elif old in scene_records and scene_records[old] == canon(scene):
                smap[old] = old
            else:
                new = old if old not in used else make_id(used)
                smap[old] = new
                item = remap_tree(scene, {old: new})
                result['scenes'].append(item)
                scene_records[new] = canon(item)
        mapping.update(smap)

        # Plan object IDs first, so variable scope references can be remapped.
        omap, duplicate_objects, new_objects = {}, set(), []
        for obj in src.get('objects', []):
            old = obj.get('id')
            sig = canon(obj)
            if isinstance(old, str) and old in object_records and object_records[old] == sig:
                omap[old] = old
                duplicate_objects.add(old)
                continue
            new = old
            if isinstance(old, str):
                if old in used: new = make_id(used)
                else: used.add(old)
                omap[old] = new
            new_objects.append(obj)
            if isinstance(old, str): object_records[new] = sig
        mapping.update(omap)

        # Variables: same ID + same name/type/scope means same variable. This
        # also handles built-in Entry variables whose visibility differs.
        vmap, variables_to_add = {}, []
        for var in src.get('variables', []):
            old = var.get('id')
            identity = (var.get('name'), var.get('variableType'), var.get('object'))
            existing = next((v for v in variable_records
                             if (v.get('name'), v.get('variableType'), v.get('object')) == identity), None)
            if existing is not None and isinstance(old, str):
                vmap[old] = existing.get('id', old)
                continue
            new = old
            if isinstance(old, str):
                if old in used: new = make_id(used)
                else: used.add(old)
                vmap[old] = new
            variables_to_add.append(var)
        mapping.update(vmap)

        # Messages, custom functions and tables: dedupe exact records; otherwise
        # allocate fresh IDs when necessary.
        for field in ('messages', 'functions', 'tables'):
            fmap = {}
            for rec in src.get(field, []):
                old = rec.get('id')
                match = next((r for r in other_records[field] if canon(r) == canon(rec)), None)
                if match is not None and isinstance(old, str):
                    fmap[old] = match.get('id', old)
                    continue
                new = old
                if isinstance(old, str):
                    if old in used: new = make_id(used)
                    else: used.add(old)
                    fmap[old] = new
                other_records[field].append(remap_tree(rec, {old: new}) if isinstance(old, str) else copy.deepcopy(rec))
            mapping.update(fmap)

        # Add newly imported objects. Picture, sound and block IDs are remapped
        # separately, then exact ID references in their JSON are updated.
        for obj in new_objects:
            local_map = dict(mapping)
            picture_map, sound_map, block_map = {}, {}, {}
            sprite = obj.get('sprite', {}) if isinstance(obj.get('sprite'), dict) else {}
            for pic in sprite.get('pictures', []) or []:
                old = pic.get('id')
                if isinstance(old, str):
                    new = old if old not in used else make_id(used)
                    if new == old: used.add(old)
                    picture_map[old] = new
            for snd in sprite.get('sounds', []) or []:
                old = snd.get('id')
                if isinstance(old, str):
                    new = old if old not in used else make_id(used)
                    if new == old: used.add(old)
                    sound_map[old] = new
            try:
                tree = json.loads(obj.get('script', '[]'))
                block_ids = set()
                def find_blocks(node):
                    if isinstance(node, dict):
                        if 'type' in node and isinstance(node.get('id'), str): block_ids.add(node['id'])
                        for value in node.values(): find_blocks(value)
                    elif isinstance(node, list):
                        for value in node: find_blocks(value)
                find_blocks(tree)
                for old in block_ids:
                    new = old if old not in used else make_id(used)
                    if new == old: used.add(old)
                    block_map[old] = new
            except Exception:
                pass
            local_map.update(picture_map); local_map.update(sound_map)
            rewritten = rewrite_object(obj, local_map, block_map)
            # Object ID and scene mapping are explicit and guaranteed.
            if isinstance(obj.get('id'), str): rewritten['id'] = omap.get(obj['id'], obj['id'])
            if isinstance(obj.get('scene'), str): rewritten['scene'] = smap.get(obj['scene'], obj['scene'])
            result['objects'].append(rewritten)

        # Add remapped variables and the other record collections.
        for var in variables_to_add:
            result['variables'].append(remap_tree(var, mapping))
            variable_records.append(remap_tree(var, mapping))
        for field in ('messages', 'functions', 'tables'):
            # other_records already contains additions; sync result from it.
            result[field] = copy.deepcopy(other_records[field])

        # Union extension/module lists without duplicates.
        for field in UNION_FIELDS:
            for value in src.get(field, []):
                rewritten = remap_tree(value, mapping)
                if rewritten not in result[field]: result[field].append(rewritten)

    # A's scene mode leaves the first project's scenes only; object mode has
    # already collapsed all imported objects to the first scene.
    if mode == 'objects':
        result['scenes'] = [copy.deepcopy(primary_scenes[0])]
        for obj in result['objects']:
            obj['scene'] = primary_scene_id

    # Preserve the first project's interface selection, but ensure it exists.
    if isinstance(result.get('interface'), dict):
        ids = {o.get('id') for o in result['objects']}
        if result['interface'].get('object') not in ids and result['objects']:
            result['interface']['object'] = result['objects'][0].get('id')
    result['name'] = (str(projects[0].get('name') or 'Entry 작품') + ' 합본')[:80]
    return result, merged_assets


def write_ent(project, assets):
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode='w:gz', compresslevel=6) as tf:
        payload = json.dumps(project, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
        info = tarfile.TarInfo(PROJECT_PATH); info.size = len(payload); info.mode = 0o644
        tf.addfile(info, io.BytesIO(payload))
        for name, data in sorted(assets.items()):
            name = safe_name(name)
            info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o644
            tf.addfile(info, io.BytesIO(data))
    return output.getvalue()


def merge_browser(items, mode):
    """items: list of (filename, base64-encoded ENT bytes)"""
    decoded = [(name, base64.b64decode(payload)) for name, payload in items]
    project, assets = merge_ent_files(decoded, None, mode)
    result = write_ent(project, assets)
    return base64.b64encode(result).decode('ascii'), len(project.get('objects', [])), len(project.get('scenes', [])), len(assets)

