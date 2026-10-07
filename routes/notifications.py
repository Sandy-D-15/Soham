from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user

from database.db import db
from models.notification import Notification
from services.notifications import (
    get_user_notifications,
    unread_count,
    mark_as_read,
    mark_all_read
)

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.route("")
@login_required
def index():
    notifications = get_user_notifications(current_user.id, limit=50)
    return render_template("notifications.html", notifications=notifications)


@notifications_bp.route("/<int:notif_id>/read", methods=["POST"])
@login_required
def read_single(notif_id):
    mark_as_read(notif_id, user_id=current_user.id)
    next_url = request.form.get("next") or request.referrer or url_for("notifications.index")
    return redirect(next_url)


@notifications_bp.route("/read-all", methods=["POST"])
@login_required
def read_all():
    mark_all_read(current_user.id)
    flash("All notifications marked as read.", "success")
    return redirect(request.referrer or url_for("notifications.index"))


@notifications_bp.route("/api/unread-count")
@login_required
def api_unread_count():
    count = unread_count(current_user.id)
    return jsonify({"count": count})
