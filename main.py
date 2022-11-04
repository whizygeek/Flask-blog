import os
import uuid
import datetime
import pyrebase
import json
import bcrypt
import tempfile
import requests
from flask import Flask, render_template, url_for, flash, redirect, request, jsonify, make_response, render_template_string
from forms import RegistrationForm, LoginForm, ResetPasswordForm
from firebase_admin import credentials, firestore, initialize_app, auth
from models.BlogModel import Blog
from functools import wraps
from flask.config import Config
from google.cloud.storage import bucket
from werkzeug.utils import secure_filename



app = Flask(__name__)

# Initialize Firestore DB
cred = credentials.Certificate('admin_key.json')
default_app = initialize_app(cred)
db = firestore.client()
users_ref = db.collection('users')
blogs_ref = db.collection('blogs')
jokes_ref = db.collection('jokes')

pb = pyrebase.initialize_app(json.load(open('fbconfig3.json')))

app.config['SECRET_KEY'] = '5a8a415f12633d390fd02b0d5b0ea3b5'
app.config['UPLOAD_FOLDER'] = 'static/img/' # folder to upload images

# before any request
# @app.before_request
# def before_request():
#     print("Run Before Every Request")

# Functions
def allow_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ['jpg', 'jpeg', 'png', 'gif']

def secure_filenames(filename):
    return f'{str(uuid.uuid4())}.'.join(filename.split('.'))

# controller
def check_token(f):
    @wraps(f)
    def wrap(*args,**kwargs):
        if not request.cookies.get('token'):
            flash(f'Sign In required!!!', 'danger')
            return redirect(url_for('login'))
        try:
            user = auth.verify_id_token(request.cookies.get('token'))
            request.user = user
            doc = users_ref.where(u'email', u'==', user["email"]).get()[0].to_dict()
            request.user["username"] = doc["username"]
        except:
            flash(f'Sign In required!!!', 'danger')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return wrap

@app.route("/", methods=['GET', 'POST'])
@app.route("/home", methods=['GET', 'POST'])
@check_token
def home():
    if request.method == 'GET':
        query = blogs_ref.order_by(u'date', direction=firestore.Query.DESCENDING)
        posts = [{"id":doc.id, "val":doc.to_dict()} for doc in query.get()]
        # joke = jokes_ref.order_by(u'createdAt', direction=firestore.Query.DESCENDING).get()[0].to_dict()
        return render_template('home.html', posts=posts)
    else:
        doc = blogs_ref.document(request.form['id']).get()
        formDict = request.form.to_dict()
        formDict["tag"] = formDict["tag"].split(",")
        blogs_ref.document(doc.id).update(formDict)
        return redirect(url_for('readBlog', blogid=doc.id))


@app.route("/about")
@check_token
def about():
    return render_template('about.html', title="about")


@app.route("/register", methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            email = form.email.data
            username = form.username.data
            password = form.password.data
            user = auth.create_user(
                email=email,
                password=password
            )
            password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            users_ref.document(str(uuid.uuid4())).set({
                "uid": user.uid, "email": email, "username": username, "password": password, "createdAt": firestore.SERVER_TIMESTAMP
            })

            flash(f'Account created for {form.email.data}!!!', 'success')
        except Exception as e:
            print(e)
            flash(f'Account could not created for {form.email.data}!!!', 'danger')
            return redirect(url_for('register'))
        return redirect(url_for('home'))
    return render_template('register.html', title='Register', form=form)


@app.route("/login", methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            user = pb.auth().sign_in_with_email_and_password(email, password)
            if not user:
                flash('Invalid username and password ','danger')    
            else:
                # password2 = users_ref.where(u'email', u'==', email).get()[0].to_dict()["password"]
                # flag = bcrypt.checkpw(password.encode('utf-8'), password2)
                # print(flag)
                jwt = user['idToken']
                flash(f'You have been logged in !', 'success')
                res = make_response(redirect(url_for('home')))
                res.set_cookie('token',jwt)
                return res
        except:
            flash('Log in unsuccessful. Please check username and password', 'danger')
            return redirect(url_for('login'))
  
    return render_template('login.html', title='Login', form=form)

@app.route("/logout")
@check_token
def logout():
    flash(f'You have been logged out !', 'success')
    res = make_response(redirect(url_for('home')))
    res.set_cookie('token','', expires=0)
    return res

@app.route("/reset-password", methods=['GET','POST'])
# @check_token
def resetPassword():
    form = ResetPasswordForm()
    if form.validate_on_submit():
        email = request.form.get('email')
        # newPassword = request.form.get('newPassword')
        try:
            pb.auth().send_password_reset_email(email)
            flash(f'Reset mail is sent to {email}!!!', 'success')
        except Exception as e:
            print(e)
            flash(f'Reset mail could not sent to {email}!!!', 'danger')
        redirect(url_for('resetPassword'))
    return render_template('resetPassword.html', title='rest password', form = form)

@app.route("/addblog", methods=['GET', 'POST'])
@check_token
def createBlog():
    if request.method == 'GET':
        return render_template('createBlog.html')
    else:
        id = str(uuid.uuid4())
        # get file from request and save it in firebase storage
        file = request.files['file']
        print("fileName: ", file.filename)
        url=""
        if file and allow_file(file.filename):
            # change the filename to unique name
            filename = secure_filenames(file.filename)
            file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(file_path)
            # save file in firebase storage
            pb.storage().child(id).put(file_path, request.cookies.get('token'))
            url = pb.storage().child(id).get_url(request.cookies.get('token'))
            os.remove(file_path)
        blog = Blog(request.form.get("author"), request.form.get(
            "title"), request.form.get("content"), request.form.get("tags").split(','),
            firestore.SERVER_TIMESTAMP, url)
        blogs_ref.document(id).set(blog.to_dict())

        return redirect(url_for('home'))


@app.route("/deleteblog", methods=['GET', 'DELETE', 'POST'])
@check_token
def deleteBlog():
    id = request.form.get("id")
    # delete file from firebase storage using public url
    pb.storage().child(id).delete(request.cookies.get('token'))
    doc = blogs_ref.document(id).get() 
    doc.reference.delete()
    return redirect(url_for('home'))


@app.route("/updateblog", methods=['GET', 'POST'])
@check_token
def updateBlog():
    id = request.form.get("id")
    doc = blogs_ref.document(id).get()
    doc_dic = doc.to_dict()
    if doc_dic["author"] == request.user["username"]:
        return render_template('editBlog.html', post={"id":id, "val":doc_dic})
    else:
        flash(f'You are not authorized to edit this post!!!', 'danger')
        return redirect(url_for('home'))

@app.route('/author/<author>',methods=['GET'])
def getBlogByAuthor(author):
    posts = [{ "id":doc.id , "val":doc.to_dict()} for doc in blogs_ref.where(u'author', u'==', author).get()]
    return render_template('home.html', posts=posts)

@app.route('/blog/<blogid>', methods=['GET', 'POST'])
@check_token
def readBlog(blogid):
    doc_blog = blogs_ref.document(blogid).get()
    blog = doc_blog.to_dict()
    comments = {}
    comment_collections = blogs_ref.document(doc_blog.id).collections()
    for collection in comment_collections:
        for doc in collection.get():
            comments[doc.id] = doc.to_dict()
    return render_template('blog_info.html', posts=[{"id":doc_blog.id, "val":blog}], comments=comments)

@app.route('/blog/comment', methods=['GET', 'POST'])
@check_token
def postComment():
    id = request.form.get("id")
    # docs = blogs_ref.where(u'id', u'==', id).get()
    # doc_dic = docs[0].to_dict()
    print("blog id in comment: ",id)
    doc = blogs_ref.document(id).get()
    doc_dic = doc.to_dict()
    blog_id = doc.id
    comment_ref = db.collection('blogs').document(doc.id).collection('comments')
    comment_ref.document(str(uuid.uuid4())).set({
        "username": request.user['username'],
        "comment": request.form.get("comment"),
        "createdAt": firestore.SERVER_TIMESTAMP
        })  
    return redirect(url_for('readBlog',blogid=request.form.get("id")))

@app.route("/blogs/daily-dose")
def getDailyDose():
    data = requests.get("https://official-joke-api.appspot.com/random_joke")
    jsonData = json.loads(data.text)
    jokes_ref.document(str(jsonData["id"])).set({
        "createdAt":firestore.SERVER_TIMESTAMP,
        "type": jsonData["type"],
        "setup": jsonData["setup"],
        "punchline": jsonData["punchline"]
        })
    return "success"

@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('500.html'), 500

if __name__ == '__main__':
    app.run(debug=True)
