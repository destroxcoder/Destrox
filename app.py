import os
from datetime import datetime, timedelta
from typing import Optional

from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_sqlalchemy import SQLAlchemy

BASE_DIR = os.path.abspath(os.path.dirname(__file__))

def create_app() -> Flask:
    app = Flask(__name__)
    app.config.setdefault("SECRET_KEY", os.environ.get("SECRET_KEY", "dev-secret-key"))
    database_path = os.environ.get("DATABASE_URL")
    if not database_path:
        database_path = "sqlite:///" + os.path.join(BASE_DIR, "app.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = database_path
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config.setdefault("ADMIN_PASSWORD", os.environ.get("ADMIN_PASSWORD", "admin123"))
    app.config.setdefault("DEFAULT_SUBSCRIPTION_DAYS", int(os.environ.get("SUBSCRIPTION_DAYS", 30)))
    app.config.setdefault("PAYMENT_QR_URL", os.environ.get("PAYMENT_QR_URL", "https://via.placeholder.com/280x280.png?text=QR"))
    app.config.setdefault(
        "PAYMENT_INSTRUCTIONS",
        os.environ.get(
            "PAYMENT_INSTRUCTIONS",
            "Paga usando Yape o transferencia bancaria a los números listados.",
        ),
    )
    app.config.setdefault("PAYMENT_ACCOUNTS", os.environ.get("PAYMENT_ACCOUNTS", "Yape: 987654321\nBCP: 123-4567890\nInterbank: 123-9876543"))
    app.config.setdefault("ADMIN_NOTIFICATION_EMAIL", os.environ.get("ADMIN_NOTIFICATION_EMAIL"))
    app.config.setdefault("SMTP_SERVER", os.environ.get("SMTP_SERVER"))
    app.config.setdefault("SMTP_PORT", int(os.environ.get("SMTP_PORT", "0") or 0))
    app.config.setdefault("SMTP_USERNAME", os.environ.get("SMTP_USERNAME"))
    app.config.setdefault("SMTP_PASSWORD", os.environ.get("SMTP_PASSWORD"))

    db.init_app(app)

    with app.app_context():
        db.create_all()

    register_routes(app)
    return app


db = SQLAlchemy()


class Client(db.Model):
    __tablename__ = "clients"

    id = db.Column(db.Integer, primary_key=True)
    phone = db.Column(db.String(32), unique=True, nullable=False)
    name = db.Column(db.String(128), nullable=False)
    sales = db.relationship("Sale", back_populates="client", lazy="dynamic")


class AccountStock(db.Model):
    __tablename__ = "account_stock"

    id = db.Column(db.Integer, primary_key=True)
    service = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(255), nullable=False)
    password = db.Column(db.String(255), nullable=False)
    profile = db.Column(db.String(64), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="Disponible")
    notes = db.Column(db.String(255), nullable=True)
    sale = db.relationship("Sale", back_populates="stock", uselist=False)


class Sale(db.Model):
    __tablename__ = "sales"

    id = db.Column(db.Integer, primary_key=True)
    client_id = db.Column(db.Integer, db.ForeignKey("clients.id"), nullable=False)
    stock_id = db.Column(db.Integer, db.ForeignKey("account_stock.id"), nullable=True)
    service = db.Column(db.String(128), nullable=False)
    payment_reference = db.Column(db.String(255), nullable=True)
    status = db.Column(db.String(32), nullable=False, default="Pendiente")
    start_date = db.Column(db.DateTime, nullable=True)
    end_date = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    client = db.relationship("Client", back_populates="sales")
    stock = db.relationship("AccountStock", back_populates="sale")

    @property
    def is_active(self) -> bool:
        return self.status == "Asignada" and (self.end_date is None or self.end_date >= datetime.utcnow())

    @property
    def is_expired(self) -> bool:
        return self.status == "Asignada" and self.end_date and self.end_date < datetime.utcnow()


WHATSAPP_NUMBER = os.environ.get("SUPPORT_WHATSAPP", "51987654321")


def send_admin_notification(app: Flask, sale: Sale) -> None:
    recipient = app.config.get("ADMIN_NOTIFICATION_EMAIL")
    if not recipient:
        app.logger.info(
            "Nuevo pedido recibido para %s (%s). Configura ADMIN_NOTIFICATION_EMAIL para enviar correos.",
            sale.service,
            sale.client.phone,
        )
        return

    from email.message import EmailMessage
    import smtplib

    server = app.config.get("SMTP_SERVER")
    port = app.config.get("SMTP_PORT")
    username = app.config.get("SMTP_USERNAME")
    password = app.config.get("SMTP_PASSWORD")

    if not server or not port:
        app.logger.warning("No se pudo enviar correo: faltan datos SMTP.")
        return

    msg = EmailMessage()
    msg["Subject"] = f"Nuevo Pedido: {sale.client.name} solicita {sale.service}"
    msg["From"] = username or "noreply@example.com"
    msg["To"] = recipient
    msg.set_content(
        (
            f"Hola!\n\n"
            f"El cliente {sale.client.name} ({sale.client.phone}) confirmó el pago del servicio {sale.service}.\n"
            "Ingresa al panel de administrador para verificar y asignar una cuenta."
        )
    )

    try:
        with smtplib.SMTP(server, port) as smtp:
            if username and password:
                smtp.starttls()
                smtp.login(username, password)
            smtp.send_message(msg)
    except Exception as exc:  # pragma: no cover - simple logging
        app.logger.error("No se pudo enviar el correo: %s", exc)


def get_logged_client() -> Optional[Client]:
    client_id = session.get("client_id")
    if not client_id:
        return None
    return Client.query.get(client_id)


def require_client_login():
    if not get_logged_client():
        flash("Inicia sesión para continuar.", "warning")
        return redirect(url_for("client_login", next=request.path))
    return None


def require_admin_login():
    if not session.get("is_admin"):
        flash("Inicia sesión como administrador.", "warning")
        return redirect(url_for("admin_login", next=request.path))
    return None


def register_routes(app: Flask) -> None:
    @app.context_processor
    def inject_globals():
        return {"whatsapp_number": WHATSAPP_NUMBER}

    @app.route("/")
    def index():
        services = (
            db.session.query(AccountStock.service)
            .filter(AccountStock.status == "Disponible")
            .distinct()
            .order_by(AccountStock.service)
            .all()
        )
        catalog = [service for (service,) in services]
        return render_template("index.html", catalog=catalog)

    @app.route("/login", methods=["GET", "POST"])
    def client_login():
        if request.method == "POST":
            phone = request.form.get("phone", "").strip()
            name = request.form.get("name", "").strip()
            if not phone:
                flash("Ingresa tu número de celular.", "danger")
            else:
                client = Client.query.filter_by(phone=phone).first()
                if not client and not name:
                    flash("Cuéntanos tu nombre para crear tu cuenta.", "warning")
                else:
                    if not client:
                        client = Client(phone=phone, name=name)
                        db.session.add(client)
                        db.session.commit()
                        flash("¡Listo! Ya creamos tu cuenta.", "success")
                    session["client_id"] = client.id
                    flash(f"Bienvenido, {client.name}.", "success")
                    next_url = request.args.get("next") or url_for("my_accounts")
                    return redirect(next_url)
        return render_template("client_login.html")

    @app.route("/logout")
    def client_logout():
        session.pop("client_id", None)
        flash("Sesión cerrada.", "info")
        return redirect(url_for("index"))

    @app.route("/buy/<service>", methods=["GET", "POST"])
    def buy_service(service: str):
        redirect_response = require_client_login()
        if redirect_response:
            return redirect_response

        client = get_logged_client()
        if request.method == "POST":
            reference = request.form.get("reference")
            sale = Sale(client_id=client.id, service=service, payment_reference=reference, status="Pendiente")
            db.session.add(sale)
            db.session.commit()
            send_admin_notification(app, sale)
            flash("¡Recibimos tu pedido! Lo verificaremos en breve.", "success")
            return redirect(url_for("order_pending"))

        payment_accounts = app.config.get("PAYMENT_ACCOUNTS", "").splitlines()
        return render_template(
            "buy_service.html",
            service=service,
            client=client,
            payment_instructions=app.config.get("PAYMENT_INSTRUCTIONS"),
            payment_qr=app.config.get("PAYMENT_QR_URL"),
            payment_accounts=payment_accounts,
        )

    @app.route("/pedido-pendiente")
    def order_pending():
        redirect_response = require_client_login()
        if redirect_response:
            return redirect_response
        return render_template("order_pending.html")

    @app.route("/mis-cuentas")
    def my_accounts():
        redirect_response = require_client_login()
        if redirect_response:
            return redirect_response
        client = get_logged_client()
        sales = (
            Sale.query.filter_by(client_id=client.id)
            .filter(Sale.stock_id.isnot(None))
            .order_by(Sale.end_date.desc().nullslast())
            .all()
        )
        return render_template("my_accounts.html", client=client, sales=sales)

    # Admin routes
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            password = request.form.get("password", "")
            if password == app.config.get("ADMIN_PASSWORD"):
                session["is_admin"] = True
                flash("Bienvenido al panel de administración.", "success")
                next_url = request.args.get("next") or url_for("admin_orders")
                return redirect(next_url)
            flash("Contraseña incorrecta.", "danger")
        return render_template("admin_login.html")

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        flash("Sesión de administrador cerrada.", "info")
        return redirect(url_for("index"))

    @app.route("/admin/pedidos")
    def admin_orders():
        redirect_response = require_admin_login()
        if redirect_response:
            return redirect_response
        orders = (
            Sale.query.filter(Sale.status == "Pendiente")
            .order_by(Sale.created_at.asc())
            .all()
        )
        return render_template("admin_orders.html", orders=orders)

    @app.route("/admin/pedidos/<int:sale_id>", methods=["GET", "POST"])
    def admin_order_detail(sale_id: int):
        redirect_response = require_admin_login()
        if redirect_response:
            return redirect_response
        sale = Sale.query.get_or_404(sale_id)
        available_accounts = AccountStock.query.filter_by(service=sale.service, status="Disponible").all()
        if request.method == "POST":
            account_id = request.form.get("account_id")
            if not account_id:
                flash("Selecciona una cuenta para asignar.", "danger")
            else:
                account = AccountStock.query.get(int(account_id))
                if not account or account.status != "Disponible" or account.service != sale.service:
                    flash("La cuenta seleccionada no está disponible.", "danger")
                else:
                    account.status = "Asignada"
                    sale.stock_id = account.id
                    sale.status = "Asignada"
                    sale.start_date = datetime.utcnow()
                    duration_days = app.config.get("DEFAULT_SUBSCRIPTION_DAYS", 30)
                    sale.end_date = sale.start_date + timedelta(days=duration_days)
                    db.session.commit()
                    flash("Cuenta asignada correctamente.", "success")
                    return redirect(url_for("admin_orders"))
        return render_template(
            "admin_order_detail.html",
            sale=sale,
            available_accounts=available_accounts,
        )

    @app.route("/admin/stock", methods=["GET", "POST"])
    def admin_stock():
        redirect_response = require_admin_login()
        if redirect_response:
            return redirect_response
        if request.method == "POST":
            service = request.form.get("service")
            email = request.form.get("email")
            password = request.form.get("password")
            profile = request.form.get("profile")
            if not all([service, email, password]):
                flash("Completa los datos obligatorios.", "danger")
            else:
                account = AccountStock(service=service, email=email, password=password, profile=profile, status="Disponible")
                db.session.add(account)
                db.session.commit()
                flash("Cuenta agregada al almacén.", "success")
                return redirect(url_for("admin_stock"))
        accounts = AccountStock.query.order_by(AccountStock.service.asc(), AccountStock.status.asc()).all()
        return render_template("admin_stock.html", accounts=accounts)

    @app.route("/admin/stock/<int:account_id>/editar", methods=["GET", "POST"])
    def admin_edit_stock(account_id: int):
        redirect_response = require_admin_login()
        if redirect_response:
            return redirect_response
        account = AccountStock.query.get_or_404(account_id)
        if request.method == "POST":
            account.service = request.form.get("service") or account.service
            account.email = request.form.get("email") or account.email
            account.password = request.form.get("password") or account.password
            account.profile = request.form.get("profile")
            account.status = request.form.get("status") or account.status
            account.notes = request.form.get("notes") or None
            db.session.commit()
            flash("Cambios guardados.", "success")
            return redirect(url_for("admin_stock"))
        return render_template("admin_edit_stock.html", account=account)

    @app.route("/admin/stock/<int:account_id>/eliminar", methods=["POST"])
    def admin_delete_stock(account_id: int):
        redirect_response = require_admin_login()
        if redirect_response:
            return redirect_response
        account = AccountStock.query.get_or_404(account_id)
        if account.status == "Asignada":
            flash("No puedes eliminar una cuenta ya asignada.", "danger")
        else:
            db.session.delete(account)
            db.session.commit()
            flash("Cuenta eliminada.", "info")
        return redirect(url_for("admin_stock"))

    @app.route("/admin/vencimientos")
    def admin_expirations():
        redirect_response = require_admin_login()
        if redirect_response:
            return redirect_response
        today = datetime.utcnow().date()
        limit = today + timedelta(days=3)
        sales = (
            Sale.query.join(Client)
            .filter(Sale.status == "Asignada")
            .filter(Sale.end_date.isnot(None))
            .filter(Sale.end_date <= datetime.combine(limit, datetime.min.time()))
            .order_by(Sale.end_date.asc())
            .all()
        )
        return render_template("admin_expirations.html", sales=sales)


app = create_app()


if __name__ == "__main__":  # pragma: no cover - manual execution
    app.run(debug=True)
