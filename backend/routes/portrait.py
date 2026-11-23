from flask import Blueprint, Response, current_app, g, jsonify, request, send_file, stream_with_context
from itsdangerous import BadData, URLSafeTimedSerializer
from werkzeug.exceptions import RequestEntityTooLarge
from werkzeug.datastructures import FileStorage

from backend.services import photo_gallery
from backend.services import portrait_workflow as workflow

bp = Blueprint('portrait', __name__, url_prefix='/api/portrait')
TOKEN_AGE = 7 * 86400


def serializer(kind):
    return URLSafeTimedSerializer(g.access_control['session_secret'], salt=f'sharp-gui/portrait/{kind}')


def sign(kind, value):
    return serializer(kind).dumps(value)


def read_token(kind, token):
    if not isinstance(token, str) or len(token) > 4096:
        raise workflow.PortraitError('portraitInvalid', 'Invalid portrait resource.')
    try:
        return serializer(kind).loads(token, max_age=TOKEN_AGE)
    except BadData as error:
        raise workflow.PortraitError('portraitExpired', 'This portrait resource has expired.', 404) from error


def file_url(media, kind='image'):
    return f'/api/portrait/media/{sign("media", [kind, media])}'


def require_output(outputs, node, key):
    entries = outputs.get(node, {}).get(key, [])
    if not entries:
        raise workflow.PortraitError('portraitNoResult', 'The workflow finished without a result. Check the current framing and try again.', 422)
    return entries[0]


def model_result(model, context):
    model_token = model['token']
    file = {'filename': f'{model_token}.ply', 'subfolder': 'portrait_sharp', 'type': 'temp'}
    return {'model': sign('model', {'token': model_token, 'source': context['source'], 'lens': context['lens']}),
            'url': file_url(file, 'model'), 'intrinsics': model['intrinsics']}


@bp.errorhandler(workflow.PortraitError)
def portrait_error(error):
    return jsonify(code=error.code, error=str(error)), error.status


@bp.errorhandler(RequestEntityTooLarge)
def portrait_upload_limit(_error):
    kind = (request.view_args or {}).get('kind')
    limit = workflow.upload_limit(kind) // (1024 * 1024)
    return jsonify(code=workflow.upload_limit_code(kind), error=f'The image exceeds {limit} MB.'), 413


@bp.get('/status')
def status():
    return jsonify(workflow.status())


@bp.get('/edit/status')
def edit_status():
    return jsonify(workflow.status(edit=True))


@bp.get('/workflows/<name>')
def visual_workflow(name):
    """查看项目随附的 ComfyUI 可视化工作流所需的节点和模型。"""
    return jsonify(workflow.visual_workflow_dependencies(name))


@bp.get('/workflows/<name>/download')
def download_visual_workflow(name):
    """下载可独立导入 ComfyUI 的画布文件。"""
    path = workflow.visual_workflow_file(name)
    return send_file(path, mimetype='application/json', as_attachment=True, download_name=f'SharpGUI-{path.name}')


@bp.get('/recent')
def recent():
    """从主机的 ComfyUI 找回更新前提交的任务。"""
    entries = []
    for item in workflow.recent_legacy_jobs():
        context = item['context']
        source = {'filename': context['source'], 'subfolder': 'sharp_gui_portrait', 'type': 'input'}
        entries.append({
            'id': context['id'], 'stage': context['stage'], 'started_at': item['started_at'], 'job': sign('job', context),
            'lens': context['lens'], 'edge': item['edge'], 'source': {'token': sign('source', source), 'url': file_url(source)},
            'model': model_result(item['model'], context) if item['model'] else None,
            'camera': item.get('camera'),
        })
    return jsonify(entries)


@bp.post('/start')
def start():
    """请求主机启动 Comfy Desktop。"""
    state = workflow.start_comfy()
    return jsonify(state=state), 202 if state == 'starting' else 200


@bp.post('/uploads/<kind>')
def upload(kind):
    request.max_content_length = workflow.upload_limit(kind) + 65536
    photo = request.files.get('image')
    if kind in {'source', 'edit-source'}:
        media, original = workflow.upload_source_photo(current_app.config['PATH_CONTEXT'], photo, edit_source=kind == 'edit-source')
        return uploaded_image('source', media, download_url=f'/api/portrait/source-original/{sign("source-original", original)}')
    media = workflow.upload_image(kind, photo)
    return uploaded_image(kind, media)


def uploaded_image(kind, media, *, download_url=None):
    response = {'token': sign(kind, media), 'url': file_url(media)}
    if download_url:
        response['download_url'] = download_url
    return jsonify(response)


@bp.get('/source-original/<token>')
def download_source_original(token):
    """以原文件名下载工作台上传的照片。"""
    original = read_token('source-original', token)
    path = workflow.uploaded_original_path(current_app.config['PATH_CONTEXT'], original['file'])
    if not path.is_file():
        raise workflow.PortraitError('portraitExpired', 'The uploaded original is unavailable.', 404)
    response = send_file(path, mimetype=workflow.PHOTO_MIME_TYPES[path.suffix], as_attachment=True, download_name=original['name'])
    response.cache_control.no_store = True
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response


@bp.post('/gallery-source/<photo_id>')
def gallery_source(photo_id):
    paths = current_app.config['PATH_CONTEXT']
    resolved = photo_gallery.resolve_photo_path(paths, photo_id)
    if not resolved:
        raise workflow.PortraitError('portraitGalleryMissing', 'The gallery photo is unavailable.', 404)
    kind = 'reference' if request.args.get('kind') == 'reference' else 'source'
    try:
        with open(resolved[1], 'rb') as photo:
            if request.args.get('kind') == 'edit-source':
                media = workflow.upload_image_stream(kind, photo, edit_source=True)
            else:
                media = workflow.upload_image_stream(kind, photo)
    except OSError as error:
        raise workflow.PortraitError('portraitGalleryMissing', 'The gallery photo is unavailable.', 404) from error
    return uploaded_image(kind, media)


@bp.post('/edit/mask')
def edit_mask():
    request.max_content_length = workflow.MAX_UPLOAD + 65536
    source = read_token('source', request.form.get('source'))
    media = workflow.prepare_edit_mask(source, request.files.get('image'))
    return jsonify(token=sign('edit-mask', {'source': source['filename'], 'media': media}))


@bp.post('/result/<action>')
def use_result(action):
    request.max_content_length = 16384
    options = request.get_json(silent=True)
    if not isinstance(options, dict) or action not in {'source', 'save'}:
        raise workflow.PortraitError('portraitInvalid', 'Choose an output image.')
    kind, media = read_token('media', options.get('result'))
    if kind != 'image' or media['type'] != 'output' or not media['filename'].lower().endswith('.png'):
        raise workflow.PortraitError('portraitInvalid', 'Choose a completed output image.')
    if action == 'source':
        with workflow.open_media(media) as image:
            return uploaded_image('source', workflow.upload_image_stream('source', image, from_result=True),
                                  download_url=f'{file_url(media)}?download=1')
    album_id = options.get('album_id')
    if not isinstance(album_id, str) or not album_id:
        raise workflow.PortraitError('portraitInvalid', 'Choose a gallery album.')
    with workflow.open_media(media) as image:
        file = FileStorage(stream=image, filename=media['filename'], content_type='image/png')
        payload, status_code = photo_gallery.upload_photos_to_album(current_app.config['PATH_CONTEXT'], album_id, [file])
    return jsonify(payload), status_code


@bp.post('/memory/release')
def release_memory():
    return jsonify(workflow.release_memory())


@bp.post('/jobs/cancel')
def cancel_job():
    request.max_content_length = 16384
    options = request.get_json(silent=True)
    if not isinstance(options, dict):
        raise workflow.PortraitError('portraitInvalid', 'Supply a portrait job or request ID.')
    if 'job' in options:
        context = read_token('job', options['job'])
        workflow.cancel_job(context['id'], context['source'])
    else:
        source = read_token('source', options.get('source'))
        workflow.cancel_job(options.get('request_id'), source['filename'], unconfirmed=True)
    return jsonify(ok=True)


@bp.post('/jobs/<stage>')
def submit(stage):
    if stage not in {'build', 'repair', 'refine', 'frame', 'edit'}:
        raise workflow.PortraitError('portraitInvalid', 'Unknown portrait stage.', 404)
    request.max_content_length = 65536
    options = request.get_json(silent=True)
    if not isinstance(options, dict):
        raise workflow.PortraitError('portraitInvalid', 'Supply portrait settings as JSON.')
    source = read_token('source', options.get('source'))
    kwargs = {}
    context = {'stage': stage, 'source': source['filename']}
    if stage == 'edit':
        reference = read_token('reference', options['reference']) if options.get('reference') else None
        masked = None
        if options.get('mask'):
            mask = read_token('edit-mask', options['mask'])
            if mask['source'] != source['filename']:
                raise workflow.PortraitError('portraitInvalid', 'Draw a mask for the current original photo.')
            masked = mask['media']
        if options.get('area') not in ('full', 'local') or (options['area'] == 'local') != bool(masked):
            raise workflow.PortraitError('editMaskRequired', 'Draw a local mask or select full image.')
        context['id'] = workflow.submit_edit(source, options, reference=reference, masked=masked)
        return jsonify(job=sign('job', context)), 202
    if stage in {'repair', 'frame'}:
        model = read_token('model', options.get('model'))
        if model['source'] != source['filename'] or model['lens'] != options.get('lens', 30):
            raise workflow.PortraitError('portraitInvalid', 'Rebuild the preview after changing the photo or lens.')
        capture = read_token('capture', options.get('capture'))
        kwargs.update(model_token=model['token'], capture=capture['filename'])
        context['capture'] = capture
    if stage == 'build':
        context['lens'] = options.get('lens', 30)
    if stage == 'refine':
        base = read_token('detail', options.get('base'))
        if base['source'] != source['filename']:
            raise workflow.PortraitError('portraitInvalid', 'Select a result from the current photo.')
        reference_token = options.get('reference')
        reference = read_token('reference', reference_token) if reference_token else base['reference']
        mask = read_token('mask', options.get('mask'))
        edge = workflow.number(options.get('reference_edge', 1536), 768, workflow.MAX_PIXEL_EDGE, integer=True)
        detail = {'target': base['target']['filename'], 'source': reference['filename'], 'mask': mask['filename'],
                  'uploaded': bool(reference_token), 'edit_mode': 'refine', 'reference_edge': edge}
        if options.get('reference_mask'):
            detail['source_mask'] = read_token('mask', options['reference_mask'])['filename']
        crop = options.get('crop')
        if crop is not None:
            if not isinstance(crop, list) or len(crop) != 4:
                raise workflow.PortraitError('portraitInvalid', 'Invalid reference crop.')
            left, top, right, bottom = (workflow.number(value, 0, 1) for value in crop)
            if right <= left or bottom <= top:
                raise workflow.PortraitError('portraitInvalid', 'The reference crop is empty.')
            detail['source_crop'] = crop
        kwargs['detail'] = detail
    context['id'] = workflow.submit(stage, source, options, **kwargs)
    return jsonify(job=sign('job', context)), 202


@bp.get('/jobs/<job>')
def job_status(job):
    context = read_token('job', job)
    job = workflow.get_job(context['id'])
    if job['state'] != 'done':
        return jsonify(job)
    outputs = job['outputs']
    stage = context['stage']
    if stage == 'build':
        model = require_output(outputs, '3', 'portrait_sharp_view')
        data = model_result(model, context)
    elif stage == 'repair':
        result = require_output(outputs, '20', 'images')
        detail = require_output(outputs, '22', 'portrait_detail')
        data = {'image': file_url(result), 'rough': file_url(context['capture']), 'reference': file_url(detail['source']),
                'base': sign('detail', {'target': detail['target'], 'reference': detail['source'], 'source': context['source']})}
    elif stage == 'frame':
        result = require_output(outputs, '10000', 'images')
        manifest = {**result, 'filename': 'transforms.json'}
        data = {'image': file_url(result), 'manifest': file_url(manifest, 'manifest')}
    elif stage == 'edit':
        prompts = outputs.get('386', {}).get('text', [])
        data = {'image': file_url(require_output(outputs, '370', 'images')),
                'prompt': prompts[0] if prompts and isinstance(prompts[0], str) else ''}
    else:
        data = {'image': file_url(require_output(outputs, '31', 'images'))}
    return jsonify(state='done', result=data)


def stream_resource(upstream, content_type, *, download=None, public=False):
    def content():
        with upstream:
            while chunk := upstream.read(256 * 1024):
                yield chunk
    response = Response(stream_with_context(content()), mimetype=content_type)
    response.call_on_close(upstream.close)
    response.headers['Cache-Control'] = 'private, max-age=3600' if public else 'private, no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    if download:
        response.headers.set('Content-Disposition', 'attachment', filename=download)
    return response


@bp.get('/media/<token>')
def media(token):
    kind, file = read_token('media', token)
    filename = file['filename']
    download = filename if request.args.get('download') == '1' else None
    mime = {'model': 'application/octet-stream', 'manifest': 'application/json'}.get(kind, 'image/png')
    return stream_resource(workflow.open_media(file), mime, download=download)


@bp.get('/renderer/<name>')
def renderer(name):
    if name not in workflow.RENDER_ASSETS:
        raise workflow.PortraitError('portraitExpired', 'Unknown renderer asset.', 404)
    return stream_resource(workflow.comfy_open(workflow.ASSET_ROOT + name), 'text/javascript', public=True)
