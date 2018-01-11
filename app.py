import datetime
from urllib.parse import urlparse, urljoin

import flask
import flask_assets
import flask_login
import flask_uploads
import flask_wtf
import flask_wtf.file
import markdown
import peewee as pw
import werkzeug
import wtforms

from playhouse import flask_utils as pw_util

app = flask.Flask(__name__, instance_relative_config=True)
app.config.from_object('config')
app.config.from_pyfile('config.py')

db_wrapper = pw_util.FlaskDB(app)

bundles = {
    'common_css': flask_assets.Bundle(
        'css/lib/normalize.css',
        'css/fonts.css',
        'css/style.css',
        output='gen/common.css',
        filters=['autoprefixer6', 'cleancss'],
    ),
}

assets = flask_assets.Environment(app)
assets.register(bundles)

login_manager = flask_login.LoginManager()
login_manager.init_app(app)
login_manager.login_view = '.login'
login_manager.login_message_category = 'info'

photo_set = flask_uploads.UploadSet('photos', flask_uploads.IMAGES)
flask_uploads.configure_uploads(app, photo_set)


def photo_resize_url(photo, size):
    if app.debug:
        return photo_set.url(photo.filename)

    return f"{photo_set.config.base_url}img{size}/{photo.filename}"


def image_resize_url(image, size):
    if app.debug:
        return f'static/images/{image}'

    return f"/static/images/img{size}/{image}"


app.jinja_env.globals['photo_resize_url'] = photo_resize_url
app.jinja_env.globals['image_resize_url'] = image_resize_url


class Photo(db_wrapper.Model):
    filename = pw.CharField()
    title = pw.CharField(null=True)
    description = pw.TextField(null=True)
    timestamp = pw.DateTimeField(default=datetime.datetime.now)

    @property
    def html_description(self):
        return markdown.markdown(self.description, output_format='html5')


class User(flask_login.UserMixin):
    pass


class LoginForm(flask_wtf.FlaskForm):
    password = wtforms.fields.PasswordField('Password')


class UploadPhotoForm(flask_wtf.FlaskForm):
    photo = wtforms.fields.FileField('Photo', validators=[
        flask_wtf.file.FileRequired(),
        flask_wtf.file.FileAllowed(photo_set, 'Images only!')
        ])
    title = wtforms.fields.StringField('Title')
    description = wtforms.fields.TextAreaField('Description')


class EditPhotoForm(flask_wtf.FlaskForm):
    photo = wtforms.fields.FileField('Photo', validators=[
        flask_wtf.file.FileAllowed(photo_set, 'Images only!')
        ])
    title = wtforms.fields.StringField('Title')
    description = wtforms.fields.TextAreaField('Description')


class ConfirmForm(flask_wtf.FlaskForm):
    pass


def flash_errors(form):
    """Flash all errors in a form."""
    for field in form:
        for error in field.errors:
            flask.flash(("Error in {} field: {}"
                        .format(field.label.text, error)),
                        'error'
                        )


@login_manager.user_loader
def load_user(user_id):
    if user_id != app.config['LOGIN']:
        return

    user = User()
    user.id = user_id
    return user


def is_safe_url(target):
    ref_url = urlparse(flask.request.host_url)
    test_url = urlparse(urljoin(flask.request.host_url, target))
    return test_url.scheme in ('http', 'https') and \
        ref_url.netloc == test_url.netloc


@app.errorhandler(404)
@app.errorhandler(500)
def not_found(e):
    return flask.render_template('error/{}.html'.format(e.code)), e.code


@app.route('/')
def index():
    return flask.render_template('index.html')


@app.route('/photo/', defaults={'page': 1})
@app.route('/photo/page/<int:page>')
def photography(page):
    photos = Photo.select().order_by(Photo.timestamp.desc()).paginate(page, 9)
    return flask.render_template('photography.html', photos=photos)


@app.route('/photo/<int:photo_id>')
def view_photo(photo_id):
    query = Photo.select().order_by(Photo.timestamp.desc())

    photo = pw_util.get_object_or_404(query, Photo.id == photo_id)

    try:
        prev = query.where(Photo.timestamp < photo.timestamp).get()

    except Photo.DoesNotExist:
        prev = None

    try:
        next = (query.order_by(Photo.timestamp.asc())
                .where(Photo.timestamp > photo.timestamp).get())

    except Photo.DoesNotExist:
        next = None

    return flask.render_template('view_photo.html',
                                 photo=photo,
                                 prev=prev,
                                 next=next)


@app.route('/me')
def me():
    return flask.render_template('me.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if flask_login.current_user.is_authenticated:
        return flask.redirect(flask.url_for('.admin'))

    if form.validate_on_submit():
        if form.password.data == app.config['LOGIN']:
            user = User()
            user.id = app.config['LOGIN']
            flask_login.login_user(user)

            next = flask.request.args.get('next')

            if not is_safe_url(next):
                return flask.abort(400)

            flask.flash('Login successful!', 'success')
            return flask.redirect(next or flask.url_for('.admin'))

        else:
            flask.flash('Wrong password.', 'error')

    return flask.render_template('login.html', form=form)


@app.route('/logout')
def logout():
    if flask_login.current_user.is_authenticated:
        flask_login.logout_user()
    else:
        flask.flash('You have to be logged in to log out! ಠ_ಠ', 'error')

    return flask.redirect(flask.url_for('.index'))


@app.route('/admin/')
@flask_login.login_required
def admin():
    return flask.render_template('admin/admin.html')


@app.route('/admin/photos/')
@flask_login.login_required
def admin_photos():
    photos = Photo.select().order_by(Photo.timestamp.desc())
    return flask.render_template('admin/photos.html', photos=photos)


@app.route('/admin/photos/<int:photo_id>', methods=['GET', 'POST'])
@flask_login.login_required
def admin_edit_photo(photo_id):
    photo = pw_util.get_object_or_404(Photo, Photo.id == photo_id)

    form = EditPhotoForm(
            werkzeug.datastructures.CombinedMultiDict((flask.request.files,
                                                       flask.request.form)),
            obj=photo
            )

    if form.validate_on_submit():
        if form.photo.data:
            photo.filename = photo_set.save(form.photo.data)

        photo.title = form.title.data
        photo.description = form.description.data

        photo.save()

        flask.flash('Photo updated!', 'success')

    else:
        flash_errors(form)

    return flask.render_template('admin/photo.html', form=form, photo=photo)


@app.route('/admin/photos/new', methods=['GET', 'POST'])
@flask_login.login_required
def admin_new_photo():
    form = UploadPhotoForm()

    if form.validate_on_submit():
        filename = photo_set.save(form.photo.data)
        photo = Photo.create(filename=filename,
                             title=form.title.data or None,
                             description=form.description.data or None
                             )

        flask.flash('Photo uploaded successfully!', 'success')
        return flask.redirect(flask.url_for('admin_edit_photo',
                                            photo_id=photo.id))

    else:
        flash_errors(form)

    return flask.render_template('admin/new_photo.html', form=form)


@app.route('/admin/photos/remove/<int:photo_id>', methods=['GET', 'POST'])
@flask_login.login_required
def admin_remove_photo(photo_id):
    photo = pw_util.get_object_or_404(Photo, Photo.id == photo_id)

    form = ConfirmForm()

    if form.validate_on_submit():
        photo.delete_instance()
        flask.flash('Photo removed.', 'success')
        return flask.redirect(flask.url_for('admin_photos'))

    else:
        flash_errors(form)

    return flask.render_template('admin/remove_photo.html',
                                 form=form,
                                 photo=photo)
