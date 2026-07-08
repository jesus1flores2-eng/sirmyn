from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, current_user, login_required
from app.models.user import User
from app.extensions import db, login_manager

auth_bp = Blueprint('auth', __name__)

# Carga el usuario desde la sesión
@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    # ============================================
    # ✅ CAMBIO 1: Usar is_admin() en lugar de id == 1
    # ============================================
    if current_user.is_authenticated:
        # Redirige según su rol
        if current_user.is_admin():  # ✅ CAMBIADO: De id == 1 a is_admin()
            return redirect(url_for('admin.dashboard'))
        elif current_user.team and current_user.team.nombre.strip().lower() == 'supervisor':
            return redirect(url_for('supervisor.dashboard_supervisor'))
        elif current_user.team:  # cualquier otra cuadrilla
            return redirect(url_for('teams.cuadrilla_dashboard'))
        else:
            flash("No tienes una cuadrilla asignada.", "warning")
            return redirect(url_for('auth.login'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        next_page = request.args.get('next')  # URL a la que intentó entrar antes de loguearse

        user = User.query.filter_by(username=username).first()
        if user and user.check_password(password):
            login_user(user)

            # Si hay una URL de origen antes del login, ve ahí
            if next_page:
                return redirect(next_page)

            # ============================================
            # ✅ CAMBIO 2: Usar is_admin() en lugar de id == 1
            # ============================================
            # Si no, redirige por rol
            if user.is_admin():  # ✅ CAMBIADO: De id == 1 a is_admin()
                return redirect(url_for('admin.dashboard'))
            elif user.team and user.team.nombre.strip().lower() == 'supervisor':
                return redirect(url_for('supervisor.dashboard_supervisor'))
            elif user.team:  # cualquier otra cuadrilla
                return redirect(url_for('teams.cuadrilla_dashboard'))
            else:
                flash("No tienes una cuadrilla asignada.", "warning")
                return redirect(url_for('auth.login'))
        else:
            flash("Usuario o contraseña incorrectos.", "danger")

    return render_template('login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash("Sesión cerrada.", "info")
    return redirect(url_for('auth.login'))