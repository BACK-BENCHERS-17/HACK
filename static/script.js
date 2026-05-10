const tg = window.Telegram.WebApp;
const mainContent = document.getElementById('main-content');
const loader = document.getElementById('loader');
const modal = document.getElementById('modal-container');
const modalBody = document.getElementById('modal-body');
const closeModal = document.querySelector('.close-modal');

const modalTitle = document.getElementById('modal-title');

let currentUser = null;
let activeTab = 'home';
let globalSettings = {};
let authenticatedUserId = null;
let sessionToken = localStorage.getItem('hack_store_auth_token');

// Initialize Telegram WebApp
tg.expand();
tg.ready();

// Auto-detect user or ask for login
if (tg.initDataUnsafe?.user) {
    currentUser = tg.initDataUnsafe.user;
    authenticatedUserId = currentUser.id;
} else {
    // If we have a stored session, use it
    authenticatedUserId = localStorage.getItem('hack_store_user_id');
}

// ──────────────────────────────────────────────────────────────────────────────
// API Helpers
// ──────────────────────────────────────────────────────────────────────────────
async function apiFetch(endpoint, method = 'GET', body = null) {
    showLoader();
    try {
        const headers = { 'Content-Type': 'application/json' };
        
        // Pass either Telegram initData or custom session token for auth
        if (tg.initData) {
            headers['X-Telegram-Init-Data'] = tg.initData;
        }
        if (sessionToken) {
            headers['X-Auth-Token'] = sessionToken;
        }

        const options = { method, headers };
        if (body) options.body = JSON.stringify(body);
        
        const res = await fetch(endpoint, options);
        
        if (res.status === 401) {
            authenticatedUserId = null;
            sessionToken = null;
            localStorage.removeItem('hack_store_auth_token');
            localStorage.removeItem('hack_store_user_id');
            renderTab();
            throw new Error("Session expired. Please login again.");
        }

        const data = await res.json();
        if (data.status === 'success' || data.status === 'ok') return data.data || data;
        throw new Error(data.message || 'API Error');
    } catch (err) {
        tg.showAlert('Error: ' + err.message);
        return null;
    } finally {
        hideLoader();
    }
}

// ──────────────────────────────────────────────────────────────────────────────
// UI Logic
// ──────────────────────────────────────────────────────────────────────────────
function showLoader() { loader.classList.remove('hidden'); }
function hideLoader() { loader.classList.add('hidden'); }

function openModal(title, html) {
    modalTitle.innerText = title;
    modalBody.innerHTML = html;
    modal.classList.remove('hidden');
    if (tg.MainButton) tg.MainButton.hide(); 
}

closeModal.onclick = () => {
    modal.classList.add('hidden');
};

// Close modal on background click
modal.onclick = (e) => {
    if (e.target === modal) modal.classList.add('hidden');
};

// ──────────────────────────────────────────────────────────────────────────────
// Routing / Tab Logic
// ──────────────────────────────────────────────────────────────────────────────
document.querySelectorAll('.nav-item').forEach(item => {
    item.onclick = () => {
        const tab = item.getAttribute('data-tab');
        if (tab === activeTab) return;
        
        document.querySelector('.nav-item.active').classList.remove('active');
        item.classList.add('active');
        activeTab = tab;
        renderTab();
    };
});

async function renderTab() {
    if (Object.keys(globalSettings).length === 0) {
        const settings = await apiFetch('/api/settings');
        if (settings) globalSettings = settings;
    }

    // Home is public, others require auth
    if (!authenticatedUserId && activeTab !== 'home') {
        showLoginRequired();
        return;
    }

    mainContent.innerHTML = '';
    if (activeTab === 'home') renderHome();
    else if (activeTab === 'store') renderStore();
    else if (activeTab === 'profile') renderProfile();
}

function showLoginRequired() {
    mainContent.innerHTML = `
        <div style="text-align: center; padding: 60px 20px;">
            <i class="fas fa-shield-alt" style="font-size: 64px; color: var(--accent-color); margin-bottom: 24px;"></i>
            <h2>Secure Login</h2>
            <p style="color: var(--text-secondary); margin: 16px 0 32px;">Please login with your mobile number to access your wallet and keys.</p>
            
            <div id="auth-step-1">
                <div style="background: var(--card-bg); padding: 16px; border-radius: 12px; border: 1px solid var(--border-color); margin-bottom: 24px;">
                    <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; text-align: left;">Mobile Number (with country code)</div>
                    <input type="text" id="login-mobile" placeholder="+919876543210" style="width: 100%; background: transparent; border: none; color: white; font-size: 18px; outline: none;">
                </div>
                <button class="btn btn-primary" onclick="requestLoginOtp()">Send OTP to Bot</button>
            </div>

            <div id="auth-step-2" class="hidden">
                <div style="background: var(--card-bg); padding: 16px; border-radius: 12px; border: 1px solid var(--border-color); margin-bottom: 24px;">
                    <div style="font-size: 11px; color: var(--text-secondary); margin-bottom: 8px; text-align: left;">Enter 6-Digit OTP</div>
                    <input type="number" id="login-otp" placeholder="123456" style="width: 100%; background: transparent; border: none; color: white; text-align: center; font-size: 24px; font-weight: 800; letter-spacing: 4px; outline: none;">
                </div>
                <button class="btn btn-primary" onclick="verifyLoginOtp()">Verify & Login</button>
                <button class="btn btn-secondary" onclick="document.getElementById('auth-step-2').classList.add('hidden'); document.getElementById('auth-step-1').classList.remove('hidden');" style="margin-top: 12px;">Back</button>
            </div>
            
            <p style="font-size: 11px; color: var(--text-secondary); margin-top: 32px;">Don't have an account? <br>Verify your number in the bot first.</p>
        </div>
    `;
}

async function requestLoginOtp() {
    const mobile = document.getElementById('login-mobile').value.trim();
    if (!mobile || mobile.length < 10) {
        tg.showAlert("Please enter a valid mobile number.");
        return;
    }
    
    const res = await apiFetch('/api/auth/request_otp', 'POST', { mobile });
    if (res) {
        document.getElementById('auth-step-1').classList.add('hidden');
        document.getElementById('auth-step-2').classList.remove('hidden');
        tg.showAlert("OTP sent! Check your Telegram bot.");
    }
}

async function verifyLoginOtp() {
    const mobile = document.getElementById('login-mobile').value.trim();
    const otp = document.getElementById('login-otp').value.trim();
    
    if (!otp || otp.length < 4) {
        tg.showAlert("Please enter the OTP.");
        return;
    }
    
    const res = await apiFetch('/api/auth/verify_otp', 'POST', { mobile, otp });
    if (res && res.token) {
        sessionToken = res.token;
        authenticatedUserId = res.user_id;
        localStorage.setItem('hack_store_auth_token', res.token);
        localStorage.setItem('hack_store_user_id', res.user_id);
        renderTab();
        tg.HapticFeedback.notificationOccurred('success');
    }
}

async function renderHome() {
    const products = await apiFetch('/api/products');
    let html = `
        <div class="banner">
            <div class="banner-content">
                <h2>Welcome to ${globalSettings.brand_name || 'Hack Store'}</h2>
                <p>Premium cheats and tools for top games. Stay undetected, stay on top.</p>
            </div>
        </div>
        <div class="section-title">
            <span>Trending Hacks</span>
            <span style="color: var(--accent-color); font-size: 13px;" onclick="activeTab='store'; renderTab();">View All</span>
        </div>
        <div class="grid">
    `;
    
    if (products) {
        products.slice(0, 4).forEach(p => {
            html += `
                <div class="product-card" onclick="showProductDetails(${p.id})">
                    <div class="product-name">${p.name}</div>
                    <div class="product-status"><i class="fas fa-check-circle"></i> Live</div>
                </div>
            `;
        });
    }
    html += '</div>';
    
    // Support section
    const supportLink = globalSettings.support_link || 'https://t.me/HackStoreSupportBot';
    html += `
        <div class="section-title" style="margin-top: 32px;">Support & Exit</div>
        <div class="grid" style="grid-template-columns: 1fr;">
            <div class="product-card" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;" onclick="tg.openTelegramLink('${supportLink}')">
                <div>
                    <div class="product-name">Need Help?</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">Open a support ticket</div>
                </div>
                <i class="fas fa-headset" style="font-size: 24px; color: var(--accent-color);"></i>
            </div>
            <div class="product-card" style="display: flex; justify-content: space-between; align-items: center;" onclick="tg.close()">
                <div>
                    <div class="product-name" style="color: var(--danger);">Exit Web Store</div>
                    <div style="font-size: 12px; color: var(--text-secondary);">Return to Telegram bot</div>
                </div>
                <i class="fas fa-sign-out-alt" style="font-size: 24px; color: var(--danger);"></i>
            </div>
        </div>
    `;
    
    mainContent.innerHTML = html;
}

async function renderStore() {
    const products = await apiFetch('/api/products');
    let html = '<div class="section-title">All Products</div><div class="grid">';
    if (products) {
        products.forEach(p => {
            html += `
                <div class="product-card" onclick="showProductDetails(${p.id})">
                    <div class="product-name">${p.name}</div>
                    <div class="product-status"><i class="fas fa-check-circle"></i> Active</div>
                </div>
            `;
        });
    }
    html += '</div>';
    mainContent.innerHTML = html;
}

async function renderProfile() {
    const user = await apiFetch(`/api/user/${authenticatedUserId}`);
    const keys = await apiFetch(`/api/user/${authenticatedUserId}/keys`);
    
    const displayName = currentUser ? `${currentUser.first_name} ${currentUser.last_name || ''}` : (user?.first_name || 'User');
    const photoUrl = currentUser?.photo_url;
    
    let html = `
        <div class="profile-header">
            ${photoUrl ? `<img src="${photoUrl}" class="avatar" style="object-fit: cover; border: 2px solid var(--accent-color);">` : `<div class="avatar">${displayName[0]}</div>`}
            <div class="user-name" style="font-size: 20px; font-weight: 700; margin-top: 10px;">${displayName}</div>
            <div style="font-size: 12px; color: var(--text-secondary); margin-top: 4px;">Telegram ID: <code>${authenticatedUserId}</code></div>
            <div class="balance-card">
                <div style="margin-bottom: 8px; color: var(--text-secondary);">Available Balance</div>
                <div class="balance-amount">₹${((user?.balance || 0)/100).toFixed(2)}</div>
                <div style="display: flex; gap: 10px; margin-top: 20px;">
                    <button class="btn btn-primary" onclick="activeTab='store'; renderTab();" style="flex: 1; margin-top: 0;">Buy Hack</button>
                    <button class="btn btn-secondary" onclick="openAddFundsModal();" style="flex: 1; margin-top: 0;">Add Fund</button>
                </div>
            </div>
            <button class="btn" style="margin-top: 20px; font-size: 12px; color: var(--danger); background: transparent; border: 1px solid var(--border-color);" onclick="authenticatedUserId=null; localStorage.removeItem('hack_store_user_id'); renderTab();">Logout / Switch</button>
        </div>
        <div class="section-title">My Purchased Keys</div>
        <div class="key-list">
    `;
    
    if (keys && keys.length > 0) {
        keys.forEach(k => {
            html += `
                <div class="key-item">
                    <div class="key-info">
                        <span style="font-weight: 600;">${k.name}</span>
                        <span style="color: var(--text-secondary);">${k.duration}</span>
                    </div>
                    <div class="key-value">${k.key_value}</div>
                    <div style="font-size: 11px; color: var(--text-secondary); margin-top: 8px;">Expires: ${k.expiry_date || 'N/A'}</div>
                </div>
            `;
        });
    } else {
        html += '<div style="text-align: center; color: var(--text-secondary); padding: 40px;">No keys found.</div>';
    }
    
    html += '</div>';
    mainContent.innerHTML = html;
}

// ──────────────────────────────────────────────────────────────────────────────
// Purchase Flow
// ──────────────────────────────────────────────────────────────────────────────
function openAddFundsModal() {
    openModal("Add Funds", `
        <div style="text-align: center; padding: 10px 0;">
            <i class="fas fa-wallet" style="font-size: 48px; color: var(--accent-color); margin-bottom: 16px;"></i>
            <p style="color: var(--text-secondary); margin-bottom: 24px;">Add funds to your wallet to purchase hacks instantly.</p>
            <div style="background: var(--card-bg); padding: 16px; border-radius: 12px; border: 1px solid var(--border-color); margin-bottom: 24px;">
                <div style="font-size: 12px; color: var(--text-secondary); margin-bottom: 8px;">Enter Amount (₹)</div>
                <input type="number" id="fund-amount" placeholder="Min ₹10" style="width: 100%; background: transparent; border: none; color: white; text-align: center; font-size: 24px; font-weight: 800; outline: none;">
            </div>
            <button class="btn btn-primary" onclick="processAddFunds()">Generate Payment QR</button>
        </div>
    `);
}

async function processAddFunds() {
    const amt = parseFloat(document.getElementById('fund-amount').value);
    if (!amt || amt < 10) {
        tg.showAlert("Minimum amount is ₹10.");
        return;
    }
    
    const orderId = 'FUND-' + Math.random().toString(36).substring(2, 10).toUpperCase();
    
    const res = await apiFetch('/generate_qr', 'POST', {
        amount: amt,
        order_id: orderId,
        payee_name: "Hack Store Funds"
    });
    
    if (!res) return;
    
    openModal("Scan to Pay", `
        <div style="text-align: center;">
            <div class="qr-container">
                <div class="qr-image">
                    <img src="data:image/png;base64,${res.qr_b64}" alt="UPI QR">
                </div>
            </div>
            <div style="margin: 20px 0;">
                <div style="font-size: 24px; font-weight: 800; margin-bottom: 4px;">₹${amt.toFixed(2)}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">Adding funds for User ID: ${user_id}</div>
            </div>
            <button class="btn btn-primary" onclick="verifyFundPayment('${orderId}', ${amt})">I Have Paid</button>
            <button class="btn btn-secondary" onclick="tg.openLink('${res.upi_link}')">Pay via UPI App</button>
        </div>
    `);
}

async function verifyFundPayment(orderId, amount) {
    const res = await apiFetch('/verify_payment', 'POST', { order_id: orderId, user_id: user_id });
    if (res && res.status === 'success') {
        openModal("Success", `
            <div style="text-align: center; padding: 20px 0;">
                <i class="fas fa-check-circle" style="font-size: 64px; color: var(--success); margin-bottom: 20px;"></i>
                <h2>Funds Added!</h2>
                <p style="color: var(--text-secondary); margin: 12px 0 24px;">₹${amount.toFixed(2)} has been added to your wallet.</p>
                <button class="btn btn-primary" onclick="activeTab='profile'; renderTab(); modal.classList.add('hidden');">View Profile</button>
            </div>
        `);
        tg.HapticFeedback.notificationOccurred('success');
    } else {
        tg.showAlert('Payment not detected yet. Please wait a few moments.');
    }
}
async function showProductDetails(prodId) {
    const products = await apiFetch('/api/products');
    const p = products.find(x => x.id === prodId);
    const plans = await apiFetch(`/api/plans/${prodId}`);
    
    let html = `
        <div class="product-detail-hero">
            <div class="product-info-header" style="margin-bottom: 12px;">
                <div class="product-status-tag" style="font-size: 12px; color: var(--success); font-weight: 600;">
                    <i class="fas fa-check-circle"></i> UNDETECTED & LIVE
                </div>
            </div>
        </div>
        <p style="color: var(--text-secondary); font-size: 14px; margin: 0 0 24px 0; line-height: 1.6; background: rgba(255,255,255,0.03); padding: 12px; border-radius: 8px; border-left: 3px solid var(--accent-color);">
            ${p.description || 'Premium hack with advanced features and anti-ban protection.'}
        </p>
        <div class="section-title">Select A Plan</div>
    `;
    
    if (plans && plans.length > 0) {
        plans.forEach(plan => {
            html += `
                <div class="plan-item" onclick="startPurchase(${plan.id}, ${plan.price}, '${plan.duration}', '${p.name}')">
                    <div>
                        <div style="font-weight: 700; font-size: 16px;">${plan.duration}</div>
                        <div style="font-size: 11px; color: var(--text-secondary); margin-top: 2px;">⚡️ Instant Key Delivery</div>
                    </div>
                    <div style="text-align: right;">
                        <div style="font-weight: 800; color: var(--accent-color); font-size: 18px;">₹${(plan.price/100).toFixed(2)}</div>
                        <div style="font-size: 10px; color: var(--success);">Best Quality</div>
                    </div>
                </div>
            `;
        });
    } else {
        html += '<div style="text-align: center; color: var(--text-secondary); padding: 20px;">Out of stock.</div>';
    }
    
    openModal(p.name, html);
}

async function startPurchase(planId, pricePaise, duration, prodName) {
    const orderId = 'WEB-' + Math.random().toString(36).substring(2, 10).toUpperCase();
    const amount = pricePaise / 100;
    
    const res = await apiFetch('/generate_qr', 'POST', {
        amount: amount,
        order_id: orderId,
        plan_id: planId,
        payee_name: "Hack Store Purchase"
    });
    
    if (!res) return;
    
    let html = `
        <div style="text-align: center;">
            <div style="background: var(--card-bg); padding: 12px; border-radius: 8px; margin-bottom: 20px;">
                <div style="font-size: 11px; color: var(--text-secondary);">Purchasing:</div>
                <div style="font-weight: 700;">${prodName} (${duration})</div>
            </div>
            
            <div class="qr-container">
                <div class="qr-image">
                    <img src="data:image/png;base64,${res.qr_b64}" alt="UPI QR">
                </div>
            </div>
            
            <div style="margin: 20px 0;">
                <div style="font-size: 24px; font-weight: 800; margin-bottom: 4px;">₹${amount.toFixed(2)}</div>
                <div style="font-size: 11px; color: var(--text-secondary);">Order ID: ${orderId}</div>
            </div>
            
            <button class="btn btn-primary" onclick="verifyWebPayment('${orderId}')">I Have Paid</button>
            <button class="btn btn-secondary" onclick="openUpiApp('${res.upi_link}')">Open UPI App</button>
        </div>
    `;
    
    openModal("Complete Payment", html);
}

function openUpiApp(link) {
    try {
        // Method 1: Telegram SDK
        tg.openLink(link, { try_instant_view: false });
        
        // Fallback: Location redirection
        setTimeout(() => {
            window.location.href = link;
        }, 800);
    } catch (e) {
        tg.showAlert("If UPI app doesn't open, please scan the QR code manually.");
    }
}

async function verifyWebPayment(orderId) {
    const res = await apiFetch('/verify_payment', 'POST', { order_id: orderId, user_id: authenticatedUserId });
    if (res && (res.status === 'success' || res.status === 'ok')) {
        const orderData = res.data || res;
        
        if (orderData.status === 'PAID_NO_STOCK') {
            openModal("Out of Stock", `
                <div style="text-align: center; padding: 20px 0;">
                    <i class="fas fa-exclamation-triangle" style="font-size: 64px; color: var(--warning); margin-bottom: 20px;"></i>
                    <h2>Payment Verified!</h2>
                    <p style="color: var(--text-secondary); margin: 12px 0 24px;">However, the product is currently out of stock. Please contact support with Order ID: <code>${orderId}</code> to receive your key manually.</p>
                    <button class="btn btn-primary" onclick="tg.openTelegramLink('${globalSettings.support_link}')">Contact Support</button>
                </div>
            `);
            return;
        }

        openModal("Success", `
            <div style="text-align: center; padding: 20px 0;">
                <i class="fas fa-check-circle" style="font-size: 64px; color: var(--success); margin-bottom: 20px;"></i>
                <h2>Purchase Successful!</h2>
                <p style="color: var(--text-secondary); margin: 12px 0 24px;">Your key has been delivered to your profile.</p>
                <button class="btn btn-primary" onclick="activeTab='profile'; renderTab(); modal.classList.add('hidden');">View My Key</button>
            </div>
        `);
        tg.HapticFeedback.notificationOccurred('success');
    } else {
        tg.showAlert('Payment not detected yet. Please wait a few moments.');
    }
}

// Initial Render
renderTab();
