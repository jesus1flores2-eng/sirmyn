from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, current_user, login_required
from app.models.user import User
from app.extensions import db, login_manager

auth_bp = Blueprint('auth', __name__)


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        if current_user.is_admin():
            return redirect(url_for('admin.dashboard'))
        elif (getattr(current_user, 'nivel', None) == 'supervisor' or
              getattr(current_user, 'rol_especifico', None) == 'supervisor' or
              getattr(current_user, 'role', None) == 'supervisor'):
            return redirect(url_for('supervisor.dashboard_supervisor'))
        elif current_user.team:
            return redirect(url_for('teams.cuadrilla_dashboard'))
        else:
            flash("No tienes una cuadrilla asignada.", "warning")
            return redirect(url_for('auth.login'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        next_page = request.args.get('next')

        # Primero intenta login normal de usuarios
        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)

            if next_page:
                return redirect(next_page)

            if user.is_admin():
                return redirect(url_for('admin.dashboard'))
            elif (getattr(user, 'nivel', None) == 'supervisor' or
                  getattr(user, 'rol_especifico', None) == 'supervisor' or
                  getattr(user, 'role', None) == 'supervisor'):
                return redirect(url_for('supervisor.dashboard_supervisor'))
            elif user.team:
                return redirect(url_for('teams.cuadrilla_dashboard'))
            else:
                flash("No tienes una cuadrilla asignada.", "warning")
                return redirect(url_for('auth.login'))

        # Si no es usuario normal, intentar login de municipio
        from app.models.municipio_config import MunicipioConfig

        municipio = MunicipioConfig.query.filter_by(usuario=username).first()
        if municipio and municipio.check_password(password):
            session['municipio_id'] = municipio.id
            session['municipio_nombre'] = municipio.nombre
            session['ver_cuadrillas'] = municipio.ver_cuadrillas
            session['ver_estados'] = municipio.ver_estados
            session['ver_inteligencia'] = municipio.ver_inteligencia
            session['ver_gps'] = municipio.ver_gps
            session['ver_encuestas'] = municipio.ver_encuestas
            session['municipio_logo'] = municipio.logo_url or 'https://imembrillos.gob.mx/Nuevo/images_upload/logotipo/e0b7f25f2202eab98bee245b8671c4fb.png'
            return redirect(url_for('municipio.dashboard'))
            
        flash("Usuario o contraseña incorrectos.", "danger")

    return render_template('login.html')


@auth_bp.route('/logout')
def logout():
    logout_user()
    session.clear()
    flash("Sesión cerrada.", "info")
    return redirect(url_for('auth.login'))
