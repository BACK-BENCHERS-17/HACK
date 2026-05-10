from flask import Flask, render_template, request, jsonify, session
import os
import re
import qrcode
import io
import base64
import logging
from datetime import datetime
from functools import wraps

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__, template_folder='web_templates', static_folder='web_static')
app.secret_key = os.environ.get('SECRET_KEY', 'hack-store-secret-' + str(os.urandom(16).hex()))

MONGO_URI = os.environ.get('MONGO_URI', 'mongodb+srv://bb:bb@cluster0.p68btnn.mongodb.net/?appName=Cluster0')
MONGO_DB = os.environ.get('MONGO_DB_NAME', 'hack_store_enterprise')
BOT_TOKEN = os.environ.get('BOT_TOKEN', '8652333340:AAFvRnoKxfk4ICAqz3ga1SkkOoJvebniprM')
ADMIN_IDS = [int(x.strip()) for x in os.environ.get('ADMIN_IDS', '8127888290,8396509436').split(',') if x.strip().isdigit()]
UPI_ID = os.environ.get('UPI_ID', 'hackstore@fam')

def get_db():
    try:
        import pymongo
        import dns.resolver
        dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
        dns.resolver.default_resolver.nameservers = ['8.8.8.8']
        client = pymongo.MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        return client[MONGO_DB]
    except Exception as e:
        logger.error(f"DB connection failed: {e}")
        return None

def require_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated

def generate_qr(amount, order_id):
    upi_link = f"upi://pay?pa={UPI_ID}&pn=HackStore&am={amount:.2f}&cu=INR&tn={order_id}"
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(upi_link)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format='PNG')
    return base64.b64encode(buf.getvalue()).decode()

@app.route('/')
def index():
    return render_template('index.html', brand_name="Hack Store", accent_color="#6366f1")

@app.route('/api/products')
def api_products():
    db = get_db()
    if not db:
        return jsonify([])
    try:
        products = list(db.products.find({"is_active": 1}).sort("name", 1))
        return jsonify([{
            "id": str(p["_id"]),
            "name": p.get("name", "Unknown"),
            "description": p.get("description", ""),
            "image_url": p.get("image_url", ""),
        } for p in products])
    except Exception as e:
        logger.error(f"Products fetch error: {e}")
        return jsonify([])

@app.route('/api/plans/<prod_id>')
def api_plans(prod_id):
    db = get_db()
    if not db:
        return jsonify([])
    try:
        plans = list(db.plans.find({"product_id": int(prod_id)}).sort("price", 1))
        return jsonify([{
            "id": str(p["_id"]),
            "duration": p.get("duration", "30 Days"),
            "price": p.get("price", 0),
        } for p in plans])
    except Exception as e:
        logger.error(f"Plans fetch error: {e}")
        return jsonify([])

@app.route('/api/user/<int:user_id>/profile')
def api_user_profile(user_id):
    db = get_db()
    if not db:
        return jsonify({"error": "DB unavailable"}), 500
    try:
        user = db.users.find_one({"user_id": user_id})
        if not user:
            return jsonify({
                "user_id": user_id,
                "first_name": "User",
                "balance": 0,
                "total_spent": 0,
            })
        return jsonify({
            "user_id": user.get("user_id"),
            "first_name": user.get("first_name", "User"),
            "username": user.get("username", ""),
            "balance": user.get("balance", 0),
            "total_spent": user.get("total_spent", 0),
            "joined_date": str(user.get("joined_date", ""))[:10],
        })
    except Exception as e:
        logger.error(f"Profile fetch error: {e}")
        return jsonify({"error": str(e)}), 500

@app.route('/api/user/<int:user_id>/keys')
def api_user_keys(user_id):
    db = get_db()
    if not db:
        return jsonify([])
    try:
        purchases = list(db.purchases.find({"user_id": user_id}).sort("_id", -1).limit(50))
        keys_data = []
        for p in purchases:
            plan = db.plans.find_one({"_id": p.get("plan_id")})
            prod = db.products.find_one({"_id": plan.get("product_id")}) if plan else None
            key = db.keys.find_one({"_id": p.get("key_id")}) if p.get("key_id") else None
            keys_data.append({
                "name": prod.get("name", "Unknown") if prod else "Unknown",
                "duration": plan.get("duration", "N/A") if plan else "N/A",
                "key_value": key.get("key_value", "N/A") if key else "N/A",
                "expiry_date": key.get("expiry_date", "") if key else "",
            })
        return jsonify(keys_data)
    except Exception as e:
        logger.error(f"Keys fetch error: {e}")
        return jsonify([])

@app.route('/api/auth/request_otp', methods=['POST'])
def api_request_otp():
    data = request.json
    mobile = data.get('mobile', '')
    if not mobile or len(mobile) < 10:
        return jsonify({'error': 'Invalid mobile number'}), 400
    
    import random
    otp = str(random.randint(100000, 999999))
    session['otp_pending'] = otp
    session['otp_mobile'] = mobile
    session['otp_time'] = datetime.now().isoformat()
    
    logger.info(f"OTP for {mobile}: {otp}")
    return jsonify({'success': True, 'message': 'OTP generated (check logs for demo)'})

@app.route('/api/auth/verify_otp', methods=['POST'])
def api_verify_otp():
    data = request.json
    mobile = data.get('mobile', '')
    otp = data.get('otp', '')
    
    if not mobile or not otp:
        return jsonify({'error': 'Missing fields'}), 400
    
    db = get_db()
    if not db:
        return jsonify({'error': 'Service unavailable'}), 503
    
    try:
        user = db.users.find_one({"phone": {"$regex": mobile[-10:]}})
        if not user:
            return jsonify({'error': 'User not found. Please verify your number in the Telegram bot first.'}), 404
        
        expected = session.get('otp_pending')
        if expected and otp == expected:
            session['user_id'] = user['user_id']
            session['user_name'] = user.get('first_name', 'User')
            return jsonify({
                'success': True,
                'token': f"web_{user['user_id']}_{datetime.now().strftime('%Y%m%d%H%M%S')}",
                'user_id': user['user_id']
            })
        return jsonify({'error': 'Invalid OTP'}), 401
    except Exception as e:
        logger.error(f"OTP verify error: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/fund/add', methods=['POST'])
@require_auth
def api_add_fund():
    data = request.json
    amount = float(data.get('amount', 0))
    user_id = session.get('user_id')
    
    if amount < 10:
        return jsonify({'error': 'Minimum amount is ₹10'}), 400
    
    import uuid
    order_id = f"WEB-{uuid.uuid4().hex[:8].upper()}"
    
    try:
        db = get_db()
        db.fund_requests.insert_one({
            "user_id": user_id,
            "order_id": order_id,
            "amount_requested": amount,
            "status": "PENDING",
            "request_date": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"Fund request error: {e}")
    
    qr_b64 = generate_qr(amount, order_id)
    upi_link = f"upi://pay?pa={UPI_ID}&pn=HackStore&am={amount:.2f}&cu=INR&tn={order_id}"
    
    return jsonify({
        'success': True,
        'order_id': order_id,
        'qr_b64': qr_b64,
        'upi_link': upi_link,
    })

@app.route('/api/purchase/generate', methods=['POST'])
@require_auth
def api_purchase_generate():
    data = request.json
    plan_id = int(data.get('plan_id', 0))
    user_id = session.get('user_id')
    
    if not plan_id:
        return jsonify({'error': 'Plan ID required'}), 400
    
    db = get_db()
    plan = db.plans.find_one({"_id": plan_id}) if db else None
    if not plan:
        return jsonify({'error': 'Plan not found'}), 404
    
    import uuid
    order_id = f"WEB-{uuid.uuid4().hex[:8].upper()}"
    amount = plan.get("price", 0) / 100
    
    try:
        db.fund_requests.insert_one({
            "user_id": user_id,
            "order_id": order_id,
            "plan_id": plan_id,
            "amount_requested": amount,
            "status": "PENDING",
            "request_date": datetime.now().isoformat(),
        })
    except Exception as e:
        logger.error(f"Purchase request error: {e}")
    
    qr_b64 = generate_qr(amount, order_id)
    upi_link = f"upi://pay?pa={UPI_ID}&pn=HackStore&am={amount:.2f}&cu=INR&tn={order_id}"
    
    return jsonify({
        'success': True,
        'order_id': order_id,
        'qr_b64': qr_b64,
        'upi_link': upi_link,
        'amount': amount,
    })

@app.route('/api/check_order/<order_id>')
def api_check_order(order_id):
    db = get_db()
    if not db:
        return jsonify({'status': 'UNKNOWN', 'error': 'DB unavailable'}), 503
    
    try:
        order = db.fund_requests.find_one({"order_id": order_id})
        if not order:
            return jsonify({'status': 'NOT_FOUND'})
        return jsonify({
            'status': order.get('status', 'PENDING'),
            'delivered_key': order.get('delivered_key', ''),
        })
    except Exception as e:
        return jsonify({'status': 'ERROR', 'error': str(e)}), 500

@app.route('/api/settings')
def api_settings():
    return jsonify({
        'brand_name': 'Hack Store',
        'support_link': 'https://t.me/HackStoreSupportBot',
        'channel_link': '',
        'accent_color': '#6366f1',
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
