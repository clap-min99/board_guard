"""Inspection archive endpoints, independent of camera/model startup."""

from flask import Blueprint, jsonify, request

from database import get_inspection_history


history_api = Blueprint("history_api", __name__)


@history_api.get("/inspection/history")
def inspection_history():
    try:
        result = get_inspection_history(
            state=request.args.get("state", "PASS"),
            filter=request.args.get("filter", "all"),
            page=int(request.args.get("page", "1")),
        )
    except ValueError as error:
        return jsonify({"error": str(error)}), 400
    response = jsonify(result)
    response.headers["Cache-Control"] = "no-store"
    return response
