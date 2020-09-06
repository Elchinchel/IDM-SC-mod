# я тоже ничего разобрать в этой каше не могу, ты не одинок'
# обещаю разгрести это барахло и вырезать остатки от лп, когда будет время
from flask import (Flask, redirect, request, render_template,
    send_from_directory, abort, make_response)
from .objects import Event, dp, DB, ExcDB, ExceptToJson, DB_general
from .lpcommands.utils import gen_secret, set_online_privacy
from .sync import lpsync, secret_fail_lp
from microvk import VkApi, VkApiResponseException
from hashlib import md5
from wtflog import warden
from typing import List, Union
import json, requests, re, time, traceback

app = Flask(__name__)

logger = warden.get_boy(__name__)

auth: str = {
    'token': '',
    'user': 0
    }

def get_mask(token:str) -> str:
        if len(token) != 85: return 'Не установлен'
        return token[:4] + "*" * 77 + token[81:]


def login_check(request, db: DB, db_gen: DB_general):
    # uid = db.duty_id
    # token = request.cookies.get('token')
    if not db_gen.installed:
        return redirect('/install')
    # if md5(f"{db_gen.vk_app_id}{uid}{db_gen.vk_app_secret}".encode()).hexdigest() != token:
    if request.cookies.get('auth') != auth['token']:
        return int_error('Ошибка авторизации, попробуй очистить cookies или перелогиниться')


def format_tokens(tokens: list) -> List[Union[str, None]]:
    for i in range(len(tokens)):
        token = re.search(r'access_token=[a-z0-9]{85}', tokens[i])
        if token: token = token[0][13:]
        elif len(tokens[i]) == 85: token = tokens[i]
        else: token = None
        tokens[i] = token
    return tokens


def check_tokens(tokens: list):
    user_ids = []
    for i in range(len(tokens)):
        try:
            user_ids.append(VkApi(tokens[i], raise_excepts=True)('users.get')[0]['id'])
            time.sleep(0.4)
        except VkApiResponseException:
            return int_error("Неверный токен, попробуйте снова")
    return user_ids



@app.route('/')
def index():
    db = DB_general()
    if db.installed: return redirect('/admin')
    return redirect('/install')



@app.route('/auth', methods=["POST"])
def do_auth():
    global auth
    user_id = check_tokens(format_tokens([request.form.get('access_token')]))
    if type(user_id) != list: return user_id
    auth['user'] = user_id[0]
    DB(user_id[0])  # ловим исключение, если юзер не в БД
    response = make_response()
    new_auth = md5(gen_secret().encode()).hexdigest()
    auth['token'] = new_auth
    response.set_cookie("auth", value=new_auth)
    response.headers['location'] = "/"
    return response, 302



@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static/img', 'favicon.png')



@app.route('/install')
def install():
    db = DB_general()
    if db.installed: return redirect('/')
    return render_template('pages/install.html')



@app.route('/api/<string:method>', methods=["POST"])
def api(method: str):

    if method == 'sync':
        return lpsync(request)

    db_gen = DB_general()

    if method == "setup_cb":#--------------------------------------------------------------
        if db_gen.installed: return redirect('/')
        
        tokens = format_tokens([request.form.get('access_token'), request.form.get('me_token')])
        
        user_id = check_tokens(tokens)[0]
        if type(user_id) != int: return user_id

        db_gen.set_user(user_id)
        db = DB(user_id)


        db.access_token = tokens[0]
        db.me_token = tokens[1]
        
        db.secret = gen_secret()
        # db_gen.vk_app_id = int(request.form.get('vk_app_id'))
        # db_gen.vk_app_secret = request.form.get('vk_app_secret')
        db_gen.host = "http://" + request.host
        db_gen.installed = True
        db.trusted_users.append(db.duty_id)
        if request.form.get('lp'):
            db_gen.mode = 'LP'
        else:
            db_gen.mode = 'CB'
        db.save()
        db_gen.save()
        if db_gen.mode == 'LP':
            return int_error(f'''(нет, не ошибка)<br>Установка прошла успешно
            <br>Этот сайт больше недоступен'''.replace('    ', ''))
        return redirect('/login?next=/admin')


    db = DB(auth['user'])

    login = login_check(request, db, db_gen)
    if login: return login


    if method == "edit_current_user":#--------------------------------------------------------------
        tokens = format_tokens([
            request.form.get('access_token', ''),
            request.form.get('me_token', '')
        ])
        if tokens[0]: db.access_token = tokens[0]
        if tokens[1]: db.me_token = tokens[1]
        db.save()
        return redirect('/admin')


    if method == 'connect_to_iris':
        uid = request.form.get('id')
        if uid: db = DB(int(uid))
        try:
            VkApi(db.access_token, raise_excepts = True)('messages.send', random_id = 0,
                message = f'+api {db.secret} {db.gen.host}/callback', peer_id = -174105461)
        except:
            return int_error('Что-то пошло не так :/')
        return redirect('/')

    if method == "edit_responses":#--------------------------------------------------------------
        for key in db.responses.keys():
            response = request.form.get(key)
            if response: db.responses[key] = response
            
        db.save()
        return redirect('/admin#Responses')


    if method == "edit_dyntemplates":
        name = request.form['temp_name']
        length = int(request.form['length'])
        i = 0
        frames = []
        while True:
            if i >= length:
                break
            frame = request.form.get(f'frame{i}')
            if frame:
                frames.append(frame)
            elif i < length:
                frames.append('Пустой кадр')
            else:
                break
            i += 1
        temp = {'name': request.form['new_name'],
            'frames': frames, 'speed': float(request.form['speed'])}
        for i in range(len(db.dyntemplates)):
            if db.dyntemplates[i]['name'] == name:
                db.dyntemplates[i].update(temp)
                break
        db.save()
        return redirect('/admin#DynTemplates')


    if method == 'add_dyntemplate':
        db.dyntemplates.append({'name': 'анимка',
            'frames': ['Отсутствует'], 'speed': 1.0})
        db.save()
        return redirect('/admin#DynTemplates')

    if method == 'delete_anim':
        name = request.form['name']
        for i in range(len(db.dyntemplates)):
            if db.dyntemplates[i]['name'] == name:
                del(db.dyntemplates[i])
                db.save()
                return redirect('/admin#DynTemplates')

    return int_error('Тебя здесь быть не должно')



@app.route('/admin/edit_user', methods = ["POST"])
def edit_user():
    return abort(403)



def db_check_user(request):
    uid = auth['user']
    if uid == 0: return redirect('/login'), 'fail'
    try:
        return DB(int(uid)), 'ok'
    except ExcDB as e:

        if e.code == 0: return int_error('В админ панель можно зайти только с аккаунта дежурного 💅🏻'), 'fail'
        else: return int_error(e), 'fail'



@app.route('/admin')
def admin():
    db_gen = DB_general()
    db, response = db_check_user(request)
    if response != 'ok': return db

    warning = 0

    login = login_check(request, db, db_gen)
    if login: return login


    users = VkApi(db.access_token)('users.get', fields = 'photo_50',
        user_ids=db.duty_id)
    if type(users) == dict:
        username = 'unknown'
        warning = {'type':'danger', 'text':'Ошибка доступа, смени токены'}
    else:
        username = f"{users[0]['first_name']} {users[0]['last_name']}"
    

    db.access_token = get_mask(db.access_token)
    db.me_token = get_mask(db.me_token)

    return render_template('pages/admin.html', db = db, users = users,
                           warn = warning, username = username)


@app.route('/login')
def login():
    return render_template('pages/login.html')



@app.route('/callback', methods=["POST"])
def callback():
    event = Event(request)

    if event.secret != event.db.secret:
        return 'Неверная секретка', 500

    d = dp.event_run(event)
    if d == "ok":
        return json.dumps({"response":"ok"}, ensure_ascii = False)
    elif type(d) == dict:
        return json.dumps(d, ensure_ascii = False)
    else:
        return r"\\\\\ашипка хэз бин произошла/////" + '\n' + d


@app.errorhandler(404)
def page_not_found(e):
    return render_template('errors/404.html'), 404

@app.errorhandler(403)
def forbidden(e):
    return render_template('errors/403.html'), 403

@app.errorhandler(500)
def int_error(e):
    return render_template('errors/500.html', error = e), 500

@app.errorhandler(ExceptToJson)
def json_error(e):
    return e.response

@app.errorhandler(VkApiResponseException)
def vk_error(e: VkApiResponseException):
    return json.dumps({
        "response": "vk_error","error_code": e.error_code, "error_message": e.error_msg
        }, ensure_ascii = False)

@app.errorhandler(ExcDB)
def db_error(e: ExcDB):
    logger.error(f'Ошибка при обработке запроса:\n{e}\n{traceback.format_exc()}')
    if e.code == 0 and auth['user'] == 0:
        return redirect('/login')
    return int_error(e.text)

@app.errorhandler(json.decoder.JSONDecodeError)
def decode_error(e):
    logger.error(f'Ошибка при декодировании данных:\n{e}\n{traceback.format_exc()}')
    return f'Произошла ошибка при декодировании данных, проверьте файлы в ICAD/database<br>Место, где споткнулся декодер: {e}'

@app.errorhandler(Exception)
def on_error(e):
    logger.error(f'Ошибка при обработке запроса:\n{e}\n{traceback.format_exc()}')
    return f'Неизвестная ошибка:\n{e}'