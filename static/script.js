const tg = window.Telegram.WebApp;
const mainContent = document.getElementById('main-content');
const loader = document.getElementById('loader');
const modal = document.getElementById('modal-container');
const modalBody = document.getElementById('modal-body');
const closeModal = document.querySelector('.close-modal');

const modalTitle = document.getElementById('modal-title');

let currentUser = null;
let activeTab = 'home';

// Initialize Telegram WebApp
tg.expand();
tg.ready();

// Fix user_id retrieval
const user_id = tg.initDataUnsafe?.user?.id || 8127888290;
if (tg.initDataUnsafe?.user) {
    currentUser = tg.initDataUnsafe.user;
}

// ──────────────────────────────────────────────────────────────────────────────
// API Helpers
// ──────────────────────────────────────────────────────────────────────────────
async function apiFetch(endpoint, method = 'GET', body = null) {
    showLoader();
    try {
        const options = { method, headers: { 'Content-Type': 'application/json' } };
        if (body) options.body = JSON.stringify(body);
        const res = await fetch(endpoint, options);
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
    mainContent.innerHTML = '';
    if (activeTab === 'home') renderHome();
    else if (activeTab === 'store') renderStore();
    else if (activeTab === 'profile') renderProfile();
}

async function renderHome() {
    const products = await apiFetch('/api/products');
    let html = `
        <div class="banner">
            <div class="banner-content">
                <h2>Welcome to Hack Store</h2>
                <p>Premium cheats and tools for top games. Stay undetected, stay on top.</p>
            </div>
        </div>
        <div class="section-title">
            <span>Trending Hacks</span>
            <span style="color: var(--accent-color); font-size: 13px;">View All</span>
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
    html += `
        <div class="section-title" style="margin-top: 32px;">Support & Exit</div>
        <div class="grid" style="grid-template-columns: 1fr;">
            <div class="product-card" style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;" onclick="tg.openTelegramLink('https://t.me/HackStoreSupportBot')">
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
    const user = await apiFetch(`/api/user/${user_id}`);
    const keys = await apiFetch(`/api/user/${user_id}/keys`);
    
    let html = `
        <div class="profile-header">
            <div class="avatar">${user?.first_name?.[0] || 'U'}</div>
            <div class="user-name">${user?.first_name || 'User'}</div>
            <div class="balance-card">
                <div>Available Balance</div>
                <div class="balance-amount">₹${((user?.balance || 0)/100).toFixed(2)}</div>
                <button class="btn btn-primary" onclick="activeTab='store'; renderTab();" style="margin-top: 16px;">Top Up / Buy</button>
            </div>
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
    
    // We need an admin session token to generate QR.
    // In a real prod environment, the backend would handle this using the active admin's credentials.
    // For the Mini App, we'll assume the backend can find an active session or we provide a default upi.
    
    // Simplified for this HACK project:
    const res = await apiFetch('/generate_qr', 'POST', {
        amount: amount,
        order_id: orderId,
        payee_name: "Hack Store Web"
    });
    
    if (!res) return;
    
    let html = `
        <div style="text-align: center;">
            <h2 style="margin-bottom: 8px;">Complete Payment</h2>
            <div style="color: var(--text-secondary); font-size: 14px; margin-bottom: 20px;">Order ID: ${orderId}</div>
            
            <div class="qr-container">
                <div class="qr-image">
                    <img src="data:image/png;base64,${res.qr_b64}" alt="UPI QR">
                </div>
            </div>
            
            <div style="margin: 20px 0;">
                <div style="font-size: 18px; font-weight: 800; margin-bottom: 4px;">₹${amount.toFixed(2)}</div>
                <div style="font-size: 12px; color: var(--text-secondary);">Scan with any UPI app</div>
            </div>
            
            <button class="btn btn-primary" onclick="verifyWebPayment('${orderId}')">I Have Paid</button>
            <button class="btn btn-secondary" onclick="tg.openLink('${res.upi_link}')">Pay via UPI App</button>
            <p style="font-size: 11px; color: var(--text-secondary); margin-top: 16px;">Please do not close this window until verified.</p>
        </div>
    `;
    
    openModal("Complete Payment", html);
}

async function verifyWebPayment(orderId) {
    const res = await apiFetch('/verify_payment', 'POST', { order_id: orderId });
    if (res && res.status === 'success') {
        openModal("Success", `
            <div style="text-align: center; padding: 20px 0;">
                <i class="fas fa-check-circle" style="font-size: 64px; color: var(--success); margin-bottom: 20px;"></i>
                <h2>Payment Verified!</h2>
                <p style="color: var(--text-secondary); margin: 12px 0 24px;">Your order has been processed successfully.</p>
                <button class="btn btn-primary" onclick="activeTab='profile'; renderTab(); modal.classList.add('hidden');">View My Keys</button>
            </div>
        `);
        tg.HapticFeedback.notificationOccurred('success');
    } else {
        tg.showAlert('Payment not detected yet. Please wait a few moments and try again.');
    }
}

// Initial Render
renderTab();
