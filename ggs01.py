import json
import os
import uuid
import requests
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, MessageHandler,
    filters, ContextTypes
)

# ================= CONFIGURATION =================
TOKEN = "8734187035:AAG2mwca0ClYrpw-sazSPWlay_-VJdmSaoA"
ADMIN_IDS = [8652607385, 6926889481]

OXAPAY_ENABLED = True
OXAPAY_API_KEY = "469NON-OAPSCL-7TRM2H-BCCEDT"
OXAPAY_MERCHANT_ID = "UQS0E6-UXUKJC-V9TLRN-WFCPVP"

# ── HOW TO SET START IMAGE ──────────────────────────────────────────────────
# METHOD 1: Use /set_image command (recommended):
#   - Send any photo to the bot, copy its file_id from logs
#   - Then use: /set_image <file_id>
#   - Or use a direct URL: /set_image https://i.imgur.com/yourimage.jpg
#   - To disable: /set_image none
#
# METHOD 2: Set directly below:
START_IMAGE = None  # e.g. "AgACAgQAAxkBAAIBB2d..." or "https://i.imgur.com/yourimage.jpg"
# ─────────────────────────────────────────────────────────────────────────────

# File paths
USERS_FILE      = "users.json"
PRODUCTS_FILE   = "products.json"
CATEGORIES_FILE = "categories.json"
INVOICES_FILE   = "invoices.json"
REVIEWS_FILE    = "reviews.json"
TICKETS_FILE    = "tickets.json"
CONFIG_FILE     = "config.json"
COUPONS_FILE    = "coupons.json"  # NEW

# ================= DATA MANAGEMENT =================
def load_data(file, default):
    if os.path.exists(file):
        with open(file, 'r') as f:
            return json.load(f)
    return default

def save_data(file, data):
    with open(file, 'w') as f:
        json.dump(data, f, indent=2)

users      = load_data(USERS_FILE,      {})
products   = load_data(PRODUCTS_FILE,   [])
categories = load_data(CATEGORIES_FILE, ["No Info", "Full Info", "All Stock"])
invoices   = load_data(INVOICES_FILE,   {})
reviews    = load_data(REVIEWS_FILE,    [])
tickets    = load_data(TICKETS_FILE,    {})
coupons    = load_data(COUPONS_FILE,    {})  # NEW: {code: {amount/percent, type, uses, max_uses, created_by, created_at}}
config     = load_data(CONFIG_FILE, {
    "welcome_text": (
        "🎉 Welcome To Cloud9 Cards 🎉\n\n"
        "• Fresh Stock Daily 📆\n"
        "• 100% Live & Verified 💚\n"
        "• Lightning Fast Service ⚡\n"
        "• 24/7 Support Team 🤝\n"
        "• Premium Deals & Rewards 🎁\n\n"
        "Checkout Our Stock ⬇️"
    ),
    "review_channel": None,
    "oxapay_api_key":     OXAPAY_API_KEY,
    "oxapay_merchant_id": OXAPAY_MERCHANT_ID,
    "start_image": START_IMAGE,
})

def save_users():     save_data(USERS_FILE,      users)
def save_products():  save_data(PRODUCTS_FILE,   products)
def save_categories():save_data(CATEGORIES_FILE, categories)
def save_invoices():  save_data(INVOICES_FILE,   invoices)
def save_reviews():   save_data(REVIEWS_FILE,    reviews)
def save_tickets():   save_data(TICKETS_FILE,    tickets)
def save_config():    save_data(CONFIG_FILE,     config)
def save_coupons():   save_data(COUPONS_FILE,    coupons)  # NEW

def get_user(user_id):
    uid = str(user_id)
    if uid not in users:
        users[uid] = {
            "balance": 0.0,
            "total_deposited": 0.0,
            "total_spent": 0.0,
            "lifetime_purchases": 0,
            "orders": [],
            "transactions": [],
            "used_coupons": []  # NEW: track which coupons this user has used
        }
        save_users()
    return users[uid]

def is_admin(user_id):
    return user_id in ADMIN_IDS

def next_product_id():
    return max([p['id'] for p in products], default=0) + 1

def next_ticket_id():
    return max([int(tid) for tid in tickets.keys()] + [0]) + 1

# ================= COUPON FUNCTIONS =================
def create_coupon(code, coupon_type, value, max_uses=None, created_by=None):
    """
    Create a new coupon code.
    coupon_type: 'fixed' or 'percent'
    value: dollar amount (for fixed) or percentage (for percent)
    max_uses: maximum redemptions (None = unlimited)
    """
    code = code.upper().strip()
    if code in coupons:
        return False, "Coupon code already exists"
    
    coupons[code] = {
        "type": coupon_type,
        "value": float(value),
        "uses": 0,
        "max_uses": max_uses,
        "created_by": created_by,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "active": True
    }
    save_coupons()
    return True, "Coupon created successfully"

def redeem_coupon(user_id, code):
    """
    Redeem a coupon for a user. Returns (success, message, amount_added)
    """
    code = code.upper().strip()
    uid = str(user_id)
    user = get_user(user_id)
    
    if code not in coupons:
        return False, "Invalid coupon code", 0.0
    
    coupon = coupons[code]
    
    if not coupon.get("active", True):
        return False, "This coupon has been deactivated", 0.0
    
    if code in user.get("used_coupons", []):
        return False, "You've already used this coupon", 0.0
    
    if coupon.get("max_uses") and coupon["uses"] >= coupon["max_uses"]:
        return False, "This coupon has reached its usage limit", 0.0
    
    # Calculate the reward
    if coupon["type"] == "fixed":
        amount = coupon["value"]
    else:  # percent - for now just give a base amount, could be applied to next purchase
        amount = coupon["value"]  # treating percent as fixed for redemption
    
    # Apply the coupon
    user["balance"] += amount
    user["total_deposited"] += amount
    user.setdefault("used_coupons", []).append(code)
    
    coupon["uses"] += 1
    
    save_users()
    save_coupons()
    
    return True, f"✅ Coupon redeemed! ${amount:.2f} added to your balance", amount

def delete_coupon(code):
    """Delete a coupon code"""
    code = code.upper().strip()
    if code in coupons:
        del coupons[code]
        save_coupons()
        return True, "Coupon deleted"
    return False, "Coupon not found"

def toggle_coupon(code):
    """Activate/deactivate a coupon"""
    code = code.upper().strip()
    if code in coupons:
        coupons[code]["active"] = not coupons[code].get("active", True)
        save_coupons()
        status = "activated" if coupons[code]["active"] else "deactivated"
        return True, f"Coupon {status}"
    return False, "Coupon not found"

# ================= OXAPAY =================
def create_oxapay_invoice(amount, order_id, user_id):
    """Create a payment invoice via OxaPay. Returns (track_id, pay_url) or (None, None)."""
    if not OXAPAY_ENABLED:
        return None, None

    merchant_api_key = config.get("oxapay_merchant_id", "").strip()
    if not merchant_api_key:
        print("[OxaPay] Missing merchant_api_key")
        return None, None

    url = "https://api.oxapay.com/v1/payment/invoice"
    headers = {
        "Content-Type":    "application/json",
        "merchant_api_key": merchant_api_key,
    }
    payload = {
        "amount":      float(amount),
        "currency":    "USD",
        "lifetime":    30,
        "order_id":    order_id,
        "description": f"Top-up for user {user_id}",
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=15)
        print(f"[OxaPay] Create status={resp.status_code} body={resp.text[:400]}")

        data = resp.json()
        if resp.status_code == 200 and data.get("status") == 200:
            inner    = data.get("data", {})
            track_id = str(inner.get("track_id", ""))
            pay_url  = inner.get("payment_url") or inner.get("payLink") or ""
            if track_id and pay_url:
                invoices[track_id] = {
                    "user_id":  user_id,
                    "amount":   float(amount),
                    "status":   "pending",
                    "order_id": order_id,
                }
                save_invoices()
                return track_id, pay_url

        print(f"[OxaPay] Failed: {data}")
        return None, None

    except Exception as e:
        print(f"[OxaPay] Exception in create: {e}")
        return None, None


def check_oxapay_invoice(track_id):
    """Check invoice status. Returns 'paid', 'waiting', 'expired', 'error', or None."""
    if not OXAPAY_ENABLED:
        return None

    merchant_api_key = config.get("oxapay_merchant_id", "").strip()
    if not merchant_api_key:
        return None

    url = f"https://api.oxapay.com/v1/payment/{track_id}"
    headers = {
        "merchant_api_key": merchant_api_key,
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        print(f"[OxaPay] Check: {resp.text[:300]}")
        data = resp.json()
        if data.get("status") == 200:
            return data.get("data", {}).get("status", "").lower()
        return None
    except Exception as e:
        print(f"[OxaPay] Exception in check: {e}")
        return None

# ================= KEYBOARDS =================
def get_main_keyboard(user_id):
    kb = [
        [InlineKeyboardButton("📄 No Info",   callback_data="cat_No Info"),
         InlineKeyboardButton("📋 Full Info", callback_data="cat_Full Info")],
        [InlineKeyboardButton("🗄️ All Stock", callback_data="cat_All Stock"),
         InlineKeyboardButton("🔍 Bin Search", callback_data="search_prompt")],
        [InlineKeyboardButton("👛 Wallet",    callback_data="wallet"),
         InlineKeyboardButton("📦 Purchased", callback_data="orders")],
        [InlineKeyboardButton("⭐ Reviews",   callback_data="reviews"),
         InlineKeyboardButton("🎫 Ticket",    callback_data="ticket_status")],
        [InlineKeyboardButton("📜 Terms",     callback_data="tos"),
         InlineKeyboardButton("👨‍💻 Dev",      callback_data="developer")],
        [InlineKeyboardButton("🛒 Request",   callback_data="request_product")],
    ]
    if is_admin(user_id):
        kb.append([InlineKeyboardButton("⚙️ Admin Panel", callback_data="admin_panel")])
    return InlineKeyboardMarkup(kb)

def get_wallet_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 Add Funds", callback_data="add_funds")],
        [InlineKeyboardButton("🎟️ Redeem Coupon", callback_data="redeem_coupon")],  # NEW
        [InlineKeyboardButton("🔙 Back", callback_data="start")],
    ])

def get_admin_panel_keyboard():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Add Product",    callback_data="admin_add_product"),
         InlineKeyboardButton("📋 Manage Products",callback_data="admin_manage_products")],
        [InlineKeyboardButton("🏷️ Manage Categories", callback_data="admin_manage_categories"),
         InlineKeyboardButton("👥 User Stats",     callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Broadcast",      callback_data="admin_broadcast"),
         InlineKeyboardButton("⚙️ Settings",       callback_data="admin_settings")],
        [InlineKeyboardButton("🎟️ Coupon Manager", callback_data="admin_coupons")],  # NEW
        [InlineKeyboardButton("🔙 Back",           callback_data="start")],
    ])

def get_coupon_admin_keyboard():  # NEW
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("➕ Create Coupon", callback_data="admin_create_coupon")],
        [InlineKeyboardButton("📋 List Coupons",  callback_data="admin_list_coupons")],
        [InlineKeyboardButton("🗑️ Delete Coupon", callback_data="admin_delete_coupon")],
        [InlineKeyboardButton("🔙 Back",          callback_data="admin_panel")],
    ])

def format_product_display(p):
    specs = p.get('specs', {})
    info_lines = []
    for k, v in specs.items():
        info_lines.append(f"{k}: {v}")
    return (
        f"🆔 ID: {p['id']}\n"
        f"📦 {p['name']}\n"
        f"💵 ${p['price']:.2f}\n"
        f"📊 Stock: {p['stock']}\n"
        f"ℹ️ {chr(10).join(info_lines)}"
    )

# ================= /START COMMAND =================
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    get_user(user_id)
    
    # Safe image handling - check config first, fall back to global
    start_image_url = config.get("start_image") or START_IMAGE
    
    if start_image_url:
        try:
            await update.message.reply_photo(
                photo=start_image_url,
                caption=config["welcome_text"],
                reply_markup=get_main_keyboard(user_id),
            )
        except Exception as e:
            print(f"[Image Error] {e}")
            # Fallback to text-only if image fails
            await update.message.reply_text(
                config["welcome_text"],
                reply_markup=get_main_keyboard(user_id),
            )
    else:
        await update.message.reply_text(
            config["welcome_text"],
            reply_markup=get_main_keyboard(user_id),
        )

# ================= ADMIN COMMANDS =================
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    await update.message.reply_text("🔐 Admin Panel", reply_markup=get_admin_panel_keyboard())

async def set_api(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /set_api <merchant_id> <api_key>")
        return
    config["oxapay_merchant_id"] = context.args[0]
    config["oxapay_api_key"]     = context.args[1]
    save_config()
    await update.message.reply_text("✅ OxaPay credentials updated.")

async def set_image(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    if not context.args:
        await update.message.reply_text("Usage: /set_image <url_or_file_id>\nOr /set_image none to disable")
        return
    
    image_value = context.args[0]
    if image_value.lower() == "none":
        config["start_image"] = None
        save_config()
        await update.message.reply_text("✅ Start image disabled")
    else:
        config["start_image"] = image_value
        save_config()
        await update.message.reply_text(f"✅ Start image set to: {image_value}")

async def add_funds(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_admin(update.effective_user.id):
        await update.message.reply_text("⛔ Admin only.")
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addfunds <user_id> <amount>")
        return
    try:
        uid = str(context.args[0])
        amt = float(context.args[1])
        user = get_user(int(uid))
        user["balance"] += amt
        user["total_deposited"] += amt
        save_users()
        await update.message.reply_text(f"✅ Added ${amt:.2f} to user {uid}")
    except Exception as e:
        await update.message.reply_text(f"Error: {e}")

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("❌ All operations cancelled.", reply_markup=get_main_keyboard(update.effective_user.id))

# ================= BUTTON CALLBACK =================
async def button_callback(query, context: ContextTypes.DEFAULT_TYPE):
    await query.answer()
    user_id = query.from_user.id
    data    = query.data
    user    = get_user(user_id)

    # Start
    if data == "start":
        start_image_url = config.get("start_image") or START_IMAGE
        
        if start_image_url:
            try:
                await query.message.reply_photo(
                    photo=start_image_url,
                    caption=config["welcome_text"],
                    reply_markup=get_main_keyboard(user_id),
                )
            except Exception as e:
                print(f"[Image Error] {e}")
                await query.edit_message_text(
                    config["welcome_text"],
                    reply_markup=get_main_keyboard(user_id),
                )
        else:
            await query.edit_message_text(
                config["welcome_text"],
                reply_markup=get_main_keyboard(user_id),
            )

    # Wallet
    elif data == "wallet":
        balance_text = (
            f"💰 Your Wallet\n\n"
            f"Balance: ${user['balance']:.2f}\n"
            f"Total Deposited: ${user['total_deposited']:.2f}\n"
            f"Total Spent: ${user['total_spent']:.2f}\n"
            f"Lifetime Purchases: {user['lifetime_purchases']}"
        )
        await query.edit_message_text(balance_text, reply_markup=get_wallet_keyboard())

    # Add funds
    elif data == "add_funds":
        context.user_data['awaiting_amount'] = True
        await query.edit_message_text(
            "💵 Enter the amount you want to add (e.g., 50):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="wallet")]]),
        )

    # NEW: Redeem coupon
    elif data == "redeem_coupon":
        context.user_data['awaiting_coupon'] = True
        await query.edit_message_text(
            "🎟️ Enter your coupon code:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="wallet")]]),
        )

    # Orders
    elif data == "orders":
        orders = user.get('orders', [])
        if not orders:
            await query.edit_message_text(
                "📦 You have no orders yet.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start")]]),
            )
        else:
            text = "📦 Your Orders:\n\n"
            for o in orders[-10:]:
                text += f"• {o.get('product_name', 'Unknown')} - ${o.get('price', 0):.2f} ({o.get('date', 'N/A')})\n"
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start")]]),
            )

    # Reviews
    elif data == "reviews":
        if not reviews:
            msg = "⭐ No reviews yet.\n\nBe the first to leave a review!"
        else:
            msg = "⭐ Recent Reviews:\n\n" + "\n".join(reviews[-10:])
        
        kb = [
            [InlineKeyboardButton("✍️ Leave a Review", callback_data="leave_review")],
            [InlineKeyboardButton("Back", callback_data="start")],
        ]
        await query.edit_message_text(msg, reply_markup=InlineKeyboardMarkup(kb))
    
    elif data == "leave_review":
        context.user_data['leaving_review'] = True
        await query.edit_message_text(
            "✍️ Leave Your Review\n\nShare your experience with our service:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="reviews")]]),
        )

    # ToS
    elif data == "tos":
        tos_text = (
            "📜 Terms of Service\n\n"
            "1. All sales are final\n"
            "2. No refunds for valid cards\n"
            "3. Use responsibly\n"
            "4. Report any issues within 24h"
        )
        await query.edit_message_text(
            tos_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start")]]),
        )

    # Developer
    elif data == "developer":
        dev_text = "👨‍💻 Developer: @YourDevHandle\n\nFor support, open a ticket!"
        await query.edit_message_text(
            dev_text,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start")]]),
        )

    # Request product
    elif data == "request_product":
        context.user_data['awaiting_request'] = True
        await query.edit_message_text(
            "🛒 Describe the product you're looking for:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="start")]]),
        )

    # Ticket status
    elif data == "ticket_status":
        user_tickets = {k: v for k, v in tickets.items() if v['user_id'] == user_id}
        if not user_tickets:
            kb = [[InlineKeyboardButton("Create Ticket", callback_data="ticket_create")],
                  [InlineKeyboardButton("Back", callback_data="start")]]
            await query.edit_message_text("🎫 You have no tickets.", reply_markup=InlineKeyboardMarkup(kb))
        else:
            text = "🎫 Your Tickets:\n\n"
            kb = []
            for tid, t in user_tickets.items():
                text += f"#{tid} - {t['status']}\n"
                kb.append([InlineKeyboardButton(f"View #{tid}", callback_data=f"ticket_view_{tid}")])
            kb.append([InlineKeyboardButton("Create New", callback_data="ticket_create")])
            kb.append([InlineKeyboardButton("Back", callback_data="start")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "ticket_create":
        context.user_data['new_ticket'] = True
        await query.edit_message_text(
            "🎫 Describe your issue:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="ticket_status")]]),
        )

    elif data.startswith("ticket_view_"):
        tid = data.split("_")[2]
        if tid in tickets:
            t = tickets[tid]
            text = f"🎫 Ticket #{tid} - {t['status']}\n\n"
            for msg in t['messages']:
                text += f"[{msg['role']}] {msg['date']}\n{msg['text']}\n\n"
            await query.edit_message_text(
                text,
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="ticket_status")]]),
            )

    # Categories
    elif data.startswith("cat_"):
        cat = data[4:]
        cat_products = [p for p in products if p.get('category') == cat and p['stock'] > 0]
        if not cat_products:
            await query.edit_message_text(
                f"📦 No products in '{cat}' category.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start")]]),
            )
        else:
            text = f"📦 {cat} Products:\n\n"
            kb = []
            for p in cat_products[:20]:
                text += f"{p['id']}. {p['name']} - ${p['price']:.2f} ({p['stock']} left)\n"
                kb.append([InlineKeyboardButton(f"Buy #{p['id']}", callback_data=f"buy_{p['id']}")])
            kb.append([InlineKeyboardButton("Back", callback_data="start")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    # Buy product
    elif data.startswith("buy_"):
        pid = int(data.split("_")[1])
        product = next((p for p in products if p['id'] == pid), None)
        if not product:
            await query.answer("Product not found", show_alert=True)
            return
        if product['stock'] <= 0:
            await query.answer("Out of stock", show_alert=True)
            return
        if user['balance'] < product['price']:
            await query.answer(f"Insufficient balance. Need ${product['price']:.2f}", show_alert=True)
            return
        
        # Process purchase
        user['balance'] -= product['price']
        user['total_spent'] += product['price']
        user['lifetime_purchases'] += 1
        product['stock'] -= 1
        
        order = {
            "product_id": pid,
            "product_name": product['name'],
            "price": product['price'],
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        user['orders'].append(order)
        
        save_users()
        save_products()
        
        delivery = product.get('delivery', {})
        content = delivery.get('content', 'No delivery info available')
        
        receipt = (
            f"✅ Purchase Successful!\n\n"
            f"Product: {product['name']}\n"
            f"Price: ${product['price']:.2f}\n"
            f"New Balance: ${user['balance']:.2f}\n\n"
            f"📦 Delivery:\n{content}"
        )
        
        await query.message.reply_text(receipt)
        await query.edit_message_text(
            "Thank you for your purchase!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start")]]),
        )

    # Search prompt
    elif data == "search_prompt":
        context.user_data['awaiting_search'] = True
        await query.edit_message_text(
            "🔍 Enter BIN number to search:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="start")]]),
        )

    # ================= ADMIN CALLBACKS =================
    elif data == "admin_panel":
        if not is_admin(user_id):
            await query.answer("Admin only", show_alert=True)
            return
        await query.edit_message_text("🔐 Admin Panel", reply_markup=get_admin_panel_keyboard())

    elif data == "admin_add_product":
        if not is_admin(user_id):
            return
        kb = []
        for cat in categories:
            kb.append([InlineKeyboardButton(cat, callback_data=f"admin_cat_{cat}")])
        kb.append([InlineKeyboardButton("Cancel", callback_data="admin_panel")])
        await query.edit_message_text("Select category:", reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("admin_cat_"):
        if not is_admin(user_id):
            return
        cat = data[10:]
        context.user_data['product_data'] = {'category': cat}
        context.user_data['add_product_step'] = 'seller'
        await query.edit_message_text(
            f"Adding product to '{cat}'\n\nEnter seller name:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]),
        )

    elif data == "admin_manage_products":
        if not is_admin(user_id):
            return
        if not products:
            await query.edit_message_text(
                "No products found.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_panel")]]),
            )
        else:
            text = "📦 Products:\n\n"
            kb = []
            for p in products[:20]:
                text += f"{p['id']}. {p['name']} (${p['price']}, stock: {p['stock']})\n"
                kb.append([InlineKeyboardButton(f"Delete #{p['id']}", callback_data=f"admin_del_{p['id']}")])
            kb.append([InlineKeyboardButton("Back", callback_data="admin_panel")])
            await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    elif data.startswith("admin_del_"):
        if not is_admin(user_id):
            return
        pid = int(data.split("_")[2])
        products[:] = [p for p in products if p['id'] != pid]
        save_products()
        await query.answer(f"Product #{pid} deleted", show_alert=True)
        await query.edit_message_text(
            "Product deleted.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_panel")]]),
        )

    elif data == "admin_manage_categories":
        if not is_admin(user_id):
            return
        text = "🏷️ Categories:\n\n" + "\n".join(f"• {c}" for c in categories)
        kb = [
            [InlineKeyboardButton("Add Category", callback_data="admin_add_cat_prompt")],
            [InlineKeyboardButton("Back", callback_data="admin_panel")],
        ]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))

    elif data == "admin_add_cat_prompt":
        if not is_admin(user_id):
            return
        context.user_data['admin_add_cat'] = True
        await query.edit_message_text(
            "Enter new category name:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]),
        )

    elif data == "admin_stats":
        if not is_admin(user_id):
            return
        total_users = len(users)
        total_products = len(products)
        total_revenue = sum(u.get('total_spent', 0) for u in users.values())
        stats = (
            f"📊 Bot Statistics\n\n"
            f"Users: {total_users}\n"
            f"Products: {total_products}\n"
            f"Total Revenue: ${total_revenue:.2f}"
        )
        await query.edit_message_text(
            stats,
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="admin_panel")]]),
        )

    elif data == "admin_broadcast":
        if not is_admin(user_id):
            return
        context.user_data['admin_broadcast'] = True
        await query.edit_message_text(
            "📢 Enter broadcast message:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]),
        )

    elif data == "admin_settings":
        if not is_admin(user_id):
            return
        kb = [
            [InlineKeyboardButton("Set Welcome Text", callback_data="admin_set_welcome_prompt")],
            [InlineKeyboardButton("Set Review Channel", callback_data="admin_set_review_prompt")],
            [InlineKeyboardButton("Back", callback_data="admin_panel")],
        ]
        await query.edit_message_text("⚙️ Settings", reply_markup=InlineKeyboardMarkup(kb))

    elif data == "admin_set_welcome_prompt":
        if not is_admin(user_id):
            return
        context.user_data['admin_set_welcome'] = True
        await query.edit_message_text(
            "Enter new welcome text:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]),
        )

    elif data == "admin_set_review_prompt":
        if not is_admin(user_id):
            return
        context.user_data['admin_set_review_channel'] = True
        await query.edit_message_text(
            "Enter review channel ID/username:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_panel")]]),
        )

    # ================= NEW: COUPON ADMIN CALLBACKS =================
    elif data == "admin_coupons":
        if not is_admin(user_id):
            return
        await query.edit_message_text("🎟️ Coupon Manager", reply_markup=get_coupon_admin_keyboard())

    elif data == "admin_create_coupon":
        if not is_admin(user_id):
            return
        context.user_data['creating_coupon'] = {'step': 'code'}
        await query.edit_message_text(
            "🎟️ Creating New Coupon\n\nStep 1: Enter coupon code (e.g., WELCOME10):",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_coupons")]]),
        )

    elif data == "admin_list_coupons":
        if not is_admin(user_id):
            return
        if not coupons:
            await query.edit_message_text(
                "No coupons created yet.",
                reply_markup=get_coupon_admin_keyboard(),
            )
        else:
            text = "🎟️ Active Coupons:\n\n"
            for code, details in coupons.items():
                status = "✅" if details.get("active", True) else "❌"
                uses_info = f"{details['uses']}"
                if details.get('max_uses'):
                    uses_info += f"/{details['max_uses']}"
                
                if details['type'] == 'fixed':
                    value_str = f"${details['value']:.2f}"
                else:
                    value_str = f"{details['value']}%"
                
                text += f"{status} {code}: {value_str} | Uses: {uses_info}\n"
            
            await query.edit_message_text(text, reply_markup=get_coupon_admin_keyboard())

    elif data == "admin_delete_coupon":
        if not is_admin(user_id):
            return
        context.user_data['deleting_coupon'] = True
        await query.edit_message_text(
            "Enter coupon code to delete:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_coupons")]]),
        )
    
    # Set start image from photo
    elif data.startswith("set_start_image_"):
        if not is_admin(user_id):
            return
        file_id = data.replace("set_start_image_", "")
        config["start_image"] = file_id
        save_config()
        await query.edit_message_text(
            f"✅ Start image updated!\n\nFile ID: `{file_id}`\n\nUsers will now see this image when they /start",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin Panel", callback_data="admin_panel")]]),
            parse_mode="Markdown"
        )

# ================= TEXT HANDLER =================
async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text    = update.message.text.strip()

    # Add funds flow
    if context.user_data.get('awaiting_amount'):
        del context.user_data['awaiting_amount']
        try:
            amount = float(text)
            if amount <= 0:
                await update.message.reply_text("Amount must be positive.")
                return
            
            order_id = str(uuid.uuid4())
            track_id, pay_url = create_oxapay_invoice(amount, order_id, user_id)
            
            if track_id and pay_url:
                await update.message.reply_text(
                    f"💳 Payment Invoice Created\n\nAmount: ${amount:.2f}\n\n"
                    f"Pay here: {pay_url}\n\n"
                    f"After payment, use /check_{track_id} to verify.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Check Payment", callback_data=f"check_{track_id}")]]),
                )
            else:
                await update.message.reply_text("Failed to create payment. Contact admin.")
        except ValueError:
            await update.message.reply_text("Invalid amount.")
        return

    # NEW: Redeem coupon flow
    if context.user_data.get('awaiting_coupon'):
        del context.user_data['awaiting_coupon']
        success, message, amount = redeem_coupon(user_id, text)
        
        if success:
            await update.message.reply_text(
                message,
                reply_markup=get_wallet_keyboard(),
            )
        else:
            await update.message.reply_text(
                f"❌ {message}",
                reply_markup=get_wallet_keyboard(),
            )
        return

    # NEW: Create coupon flow (admin only)
    if context.user_data.get('creating_coupon') and is_admin(user_id):
        coupon_data = context.user_data['creating_coupon']
        step = coupon_data.get('step')
        
        if step == 'code':
            coupon_data['code'] = text.upper().strip()
            coupon_data['step'] = 'type'
            kb = [
                [InlineKeyboardButton("Fixed Amount ($)", callback_data="coupon_type_fixed")],
                [InlineKeyboardButton("Percentage (%)", callback_data="coupon_type_percent")],
                [InlineKeyboardButton("Cancel", callback_data="admin_coupons")],
            ]
            await update.message.reply_text(
                f"Code: {coupon_data['code']}\n\nStep 2: Select coupon type:",
                reply_markup=InlineKeyboardMarkup(kb),
            )
            return
        
        elif step == 'value':
            try:
                coupon_data['value'] = float(text)
                coupon_data['step'] = 'max_uses'
                await update.message.reply_text(
                    f"Code: {coupon_data['code']}\n"
                    f"Type: {coupon_data['type']}\n"
                    f"Value: {coupon_data['value']}\n\n"
                    f"Step 4: Enter max uses (or 'unlimited'):",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_coupons")]]),
                )
            except ValueError:
                await update.message.reply_text("Invalid value. Enter a number:")
            return
        
        elif step == 'max_uses':
            if text.lower() == 'unlimited':
                coupon_data['max_uses'] = None
            else:
                try:
                    coupon_data['max_uses'] = int(text)
                except ValueError:
                    await update.message.reply_text("Invalid. Enter a number or 'unlimited':")
                    return
            
            # Create the coupon
            success, message = create_coupon(
                coupon_data['code'],
                coupon_data['type'],
                coupon_data['value'],
                coupon_data['max_uses'],
                user_id
            )
            
            del context.user_data['creating_coupon']
            
            if success:
                summary = (
                    f"✅ Coupon Created!\n\n"
                    f"Code: {coupon_data['code']}\n"
                    f"Type: {coupon_data['type']}\n"
                    f"Value: {coupon_data['value']}\n"
                    f"Max Uses: {coupon_data['max_uses'] or 'Unlimited'}"
                )
                await update.message.reply_text(summary, reply_markup=get_coupon_admin_keyboard())
            else:
                await update.message.reply_text(f"❌ {message}", reply_markup=get_coupon_admin_keyboard())
            return

    # NEW: Delete coupon flow (admin only)
    if context.user_data.get('deleting_coupon') and is_admin(user_id):
        del context.user_data['deleting_coupon']
        success, message = delete_coupon(text)
        await update.message.reply_text(
            f"{'✅' if success else '❌'} {message}",
            reply_markup=get_coupon_admin_keyboard(),
        )
        return

    # Search BIN
    if context.user_data.get('awaiting_search'):
        del context.user_data['awaiting_search']
        results = [p for p in products if text in str(p.get('specs', {}).get('BIN', ''))]
        if not results:
            await update.message.reply_text(
                f"No products found for BIN: {text}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start")]]),
            )
        else:
            msg = f"🔍 Results for BIN {text}:\n\n"
            kb = []
            for p in results[:10]:
                msg += f"{p['id']}. {p['name']} - ${p['price']:.2f}\n"
                kb.append([InlineKeyboardButton(f"Buy #{p['id']}", callback_data=f"buy_{p['id']}")])
            kb.append([InlineKeyboardButton("Back", callback_data="start")])
            await update.message.reply_text(msg, reply_markup=InlineKeyboardMarkup(kb))
        return

    # Product request
    if context.user_data.get('awaiting_request'):
        del context.user_data['awaiting_request']
        await update.message.reply_text(
            f"✅ Request submitted: {text}\nAdmins will review it.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="start")]]),
        )
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_message(admin, f"🛒 Product Request from {user_id}:\n{text}")
            except Exception:
                pass
        return

    # New ticket
    if context.user_data.get('new_ticket'):
        del context.user_data['new_ticket']
        tid = next_ticket_id()
        tickets[str(tid)] = {
            "id":       tid,
            "user_id":  user_id,
            "status":   "open",
            "messages": [{"role": "user", "text": text, "date": datetime.now().strftime("%Y-%m-%d %H:%M")}],
        }
        save_tickets()
        await update.message.reply_text(
            f"✅ Ticket #{tid} created. Admins will reply soon.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Back", callback_data="ticket_status")]]),
        )
        for admin in ADMIN_IDS:
            try:
                await context.bot.send_message(admin, f"🎫 New ticket #{tid} from {user_id}:\n{text}")
            except Exception:
                pass
        return

    # Leave review
    if context.user_data.get('leaving_review'):
        del context.user_data['leaving_review']
        username = update.effective_user.username or update.effective_user.first_name or "Anonymous"
        review_text = f"⭐ {username}: {text}"
        reviews.append(review_text)
        save_reviews()
        
        await update.message.reply_text(
            "✅ Thank you for your review!",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("View Reviews", callback_data="reviews")]]),
        )
        
        # Post to review channel if configured
        review_channel = config.get("review_channel")
        if review_channel:
            try:
                await context.bot.send_message(review_channel, review_text)
            except Exception as e:
                print(f"Failed to post review to channel: {e}")
        return

    # Admin reply to ticket
    if context.user_data.get('reply_ticket') and is_admin(user_id):
        tid = context.user_data.pop('reply_ticket')
        if str(tid) in tickets:
            tickets[str(tid)]['messages'].append({"role": "admin", "text": text, "date": datetime.now().strftime("%Y-%m-%d %H:%M")})
            save_tickets()
            await update.message.reply_text(f"✅ Reply sent for ticket #{tid}.")
            try:
                await context.bot.send_message(tickets[str(tid)]['user_id'], f"📩 Admin replied to ticket #{tid}:\n\n{text}")
            except Exception:
                pass
        else:
            await update.message.reply_text("Ticket not found.")
        return

    # Admin: add category
    if context.user_data.get('admin_add_cat') and is_admin(user_id):
        del context.user_data['admin_add_cat']
        if text not in categories:
            categories.append(text)
            save_categories()
            await update.message.reply_text(
                f"✅ Category '{text}' added.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin", callback_data="admin_panel")]]),
            )
        else:
            await update.message.reply_text("Category already exists.")
        return

    # Admin: broadcast
    if context.user_data.get('admin_broadcast') and is_admin(user_id):
        del context.user_data['admin_broadcast']
        count = 0
        for uid in users.keys():
            try:
                await context.bot.send_message(int(uid), f"📢 Broadcast\n\n{text}")
                count += 1
            except Exception:
                pass
        await update.message.reply_text(f"✅ Broadcast sent to {count} users.")
        return

    # Admin: set welcome text
    if context.user_data.get('admin_set_welcome') and is_admin(user_id):
        del context.user_data['admin_set_welcome']
        config["welcome_text"] = text.replace('\\n', '\n')
        save_config()
        await update.message.reply_text(
            "✅ Welcome text updated.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin", callback_data="admin_panel")]]),
        )
        return

    # Admin: set review channel
    if context.user_data.get('admin_set_review_channel') and is_admin(user_id):
        del context.user_data['admin_set_review_channel']
        config["review_channel"] = text.strip()
        save_config()
        await update.message.reply_text(
            f"✅ Review channel set to {text.strip()}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin", callback_data="admin_panel")]]),
        )
        return

    # Add product wizard
    if context.user_data.get('add_product_step'):
        await add_product_wizard(update, context, text)
        return

    await update.message.reply_text("Unknown command. Use /start")

# Handle coupon type selection callback
async def coupon_type_callback(query, context, coupon_type):
    user_id = query.from_user.id
    if not is_admin(user_id):
        return
    
    if 'creating_coupon' in context.user_data:
        context.user_data['creating_coupon']['type'] = coupon_type
        context.user_data['creating_coupon']['step'] = 'value'
        
        prompt = "Step 3: Enter value (dollar amount):" if coupon_type == "fixed" else "Step 3: Enter value (percentage, e.g. 10 for 10%):"
        
        await query.edit_message_text(
            f"Code: {context.user_data['creating_coupon']['code']}\n"
            f"Type: {coupon_type}\n\n{prompt}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Cancel", callback_data="admin_coupons")]]),
        )

# Modified button_callback to include coupon type selection
async def button_callback_wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data
    
    # Handle coupon type selection
    if data == "coupon_type_fixed":
        await coupon_type_callback(query, context, "fixed")
        await query.answer()
        return
    elif data == "coupon_type_percent":
        await coupon_type_callback(query, context, "percent")
        await query.answer()
        return
    
    # Handle all other callbacks
    await button_callback(query, context)

# ================= ADD PRODUCT WIZARD =================
async def add_product_wizard(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    if not is_admin(update.effective_user.id):
        return
    step         = context.user_data.get('add_product_step')
    product_data = context.user_data.setdefault('product_data', {})

    if step == 'seller':
        product_data['Seller'] = text
        context.user_data['add_product_step'] = 'name'
        await update.message.reply_text("Product name:")
        return

    if step == 'name':
        product_data['Name'] = text
        context.user_data['add_product_step'] = 'quantity'
        await update.message.reply_text("Quantity (stock):")
        return

    if step == 'quantity':
        try:
            product_data['quantity'] = int(text)
            context.user_data['add_product_step'] = 'price'
            await update.message.reply_text("Price per item (e.g. 19.99):")
        except ValueError:
            await update.message.reply_text("Enter a whole number.")
        return

    if step == 'price':
        try:
            product_data['price'] = float(text)
            context.user_data['add_product_step'] = 'country'
            await update.message.reply_text("Country:")
        except ValueError:
            await update.message.reply_text("Invalid price. Use numbers like 19.99")
        return

    for field, (next_step, prompt) in [
        ('country', ('bin',      "BIN number:")),
        ('bin',     ('brand',    "Brand:")),
        ('brand',   ('type',     "Type:")),
        ('type',    ('bank',     "Bank:")),
        ('bank',    ('fullz',    "FULLZ Availability (YES/NO):")),
        ('fullz',   ('delivery', "Delivery content (text to send after purchase):")),
    ]:
        if step == field:
            product_data[field.capitalize()] = text
            context.user_data['add_product_step'] = next_step
            await update.message.reply_text(prompt)
            return

    if step == 'delivery':
        try:
            product = {
                'id':       next_product_id(),
                'category': product_data.get('category', 'No Info'),
                'name':     product_data.get('Name',     'Unknown'),
                'price':    product_data.get('price',    0.0),
                'stock':    product_data.get('quantity', 0),
                'specs': {
                    'Seller':  product_data.get('Seller',  'N/A'),
                    'Country': product_data.get('Country', 'N/A'),
                    'BIN':     product_data.get('Bin',     product_data.get('BIN', 'N/A')),
                    'Brand':   product_data.get('Brand',   'N/A'),
                    'Type':    product_data.get('Type',    'N/A'),
                    'Bank':    product_data.get('Bank',    'N/A'),
                    'Fullz':   product_data.get('Fullz',   'N/A'),
                },
                'delivery': {'type': 'text', 'content': text},
            }
            products.append(product)
            save_products()
            await update.message.reply_text(
                f"✅ Product added!\n\n{format_product_display(product)}",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("Admin", callback_data="admin_panel")]]),
            )
        except Exception as e:
            await update.message.reply_text(f"Error saving product: {e}")
        finally:
            context.user_data.pop('add_product_step', None)
            context.user_data.pop('product_data',     None)
        return

# ================= PHOTO HANDLER (for easy start image setup) =================
async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    # Get the largest photo file_id
    photo = update.message.photo[-1]
    file_id = photo.file_id
    
    kb = [
        [InlineKeyboardButton("✅ Yes, Set as Start Image", callback_data=f"set_start_image_{file_id}")],
        [InlineKeyboardButton("❌ No, Cancel", callback_data="admin_panel")],
    ]
    
    await update.message.reply_text(
        f"📸 Photo received!\n\nFile ID: `{file_id}`\n\nSet this as the start image?",
        reply_markup=InlineKeyboardMarkup(kb),
        parse_mode="Markdown"
    )

# ================= MAIN =================
def main():
    app = Application.builder().token(TOKEN).build()

    app.add_handler(CommandHandler("start",     start))
    app.add_handler(CommandHandler("admin",     admin_command))
    app.add_handler(CommandHandler("set_api",   set_api))
    app.add_handler(CommandHandler("set_image", set_image))
    app.add_handler(CommandHandler("addfunds",  add_funds))
    app.add_handler(CommandHandler("cancel",    cancel))

    app.add_handler(CallbackQueryHandler(button_callback_wrapper))
    app.add_handler(MessageHandler(filters.PHOTO, photo_handler))  # Handle photos for easy image setup
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_handler))

    print("✅ Bot is running with coupon support. Type /start")
    app.run_polling()

if __name__ == "__main__":
    main()
