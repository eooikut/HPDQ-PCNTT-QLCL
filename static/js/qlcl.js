/**
 * 1. CONSTANTS & CONFIGURATION
 * Định nghĩa các hằng số dùng chung toàn hệ thống
 */
const KEYS = {
    SURFACE_AUTO: ['MI', 'HPrScale', 'PRScale', 'HOLE', 'RIP', 'BRUS', 'LC', 'SCRT'],
    SURFACE_MANUAL: ['oil', 'rust', 'scratch_m', 'dirt', 'mark', 'scale', 'other_s'],
    GEO_AUTO: ['Flatness', 'Crown', 'Wedge', 'ThickDiff', 'WidthDiff'],
    GEO_MANUAL: ['telescope'],
    PROP_AUTO: ['YieldPoint', 'Tensile', 'Elongation', 'Hardness', 'C', 'Mn', 'Si', 'P', 'S'],
    APP_MANUAL: ['strap', 'label_tag', 'packaging', 'edge_cond', 'coil_shape']
};

// Thứ tự hiển thị thống nhất trên mọi biểu đồ
const UNIFIED_KEYS = {
    SURFACE: [...KEYS.SURFACE_MANUAL, ...KEYS.SURFACE_AUTO],
    GEO:     [...KEYS.GEO_MANUAL,     ...KEYS.GEO_AUTO],
    PROP:    [...KEYS.PROP_AUTO],
    APP:     [...KEYS.APP_MANUAL]
};

const DEFECT_NAMES = {
    'MI': 'Ngậm xỉ đúc', 'HPrScale': 'Xỉ sơ cấp HP', 'PRScale': 'Xỉ sơ cấp PR',
    'HOLE': 'Lỗ thủng', 
    'RIP': 'Rách bề mặt', 'BRUS': 'Vết Hằn trục',
    'LC': 'Nứt dọc', 'SCRT': 'Xước bề mặt',
    'oil': 'Gấp nếp', 'rust': 'Nếp Nhăn', 'scratch_m': 'Vết hằn Pinch Roll',

    'dirt': 'Gãy mặt', 'mark': 'Xỉ thứ cấp', 'scale': 'Xỉ cán', 'other_s': 'Xỉ muối tiêu',
    'Flatness': 'Độ phẳng', 'Crown': 'Độ vồng', 'Wedge': 'Độ nêm',
    'ThickDiff': 'Sai lệch dày', 'WidthDiff': 'Sai lệch rộng',
    'telescope': 'Cong cạnh',
    'YieldPoint': 'GH Chảy', 'Tensile': 'GH Bền', 'Elongation': 'Độ giãn',
    'Hardness': 'Độ cứng', 'C': 'Carbon', 'Mn': 'Mangan', 'Si': 'Silic', 'P': 'Photpho', 'S': 'Lưu huỳnh',
    'strap': 'Khuyết biên', 'label_tag': 'Bava biên', 'packaging': 'Vỡ biên',
    'edge_cond': 'Sổ vòng', 'coil_shape': 'Loa cuộn'
};

const PAGE_SIZE = 50;

/**
 * 2. GLOBAL STATE
 * Quản lý trạng thái ứng dụng
 */
let ALL_IDS_LIST = [], CURRENT_VIEW_LIST = [], FULL_PAGE = 1;
let MANUAL_CONFIG = null;
let INPUT_TEMP_DATA = {}; 
let CURRENT_INPUT_COIL = null;
let ORIGINAL_SNAPSHOT = {}; 
let inputCharts = { surf: null, geo: null, prop: null, app: null };
let hoverState = { chartId: null, index: -1, value: -1 };

// Các biến Modal
let MODAL_ALL=[], MODAL_FILT=[], MODAL_PAGE=1;
let mc1=null, mc2=null, mc3=null, mc4=null;

/**
 * 3. LOGIC CỐT LÕI (CALCULATION & FILTER)
 */
function calculateSummary() {
    const allIds = Object.keys(RADAR_DATA);
    ALL_IDS_LIST = allIds;
    document.getElementById('totalCoils').innerText = allIds.length;

    // Sử dụng Set để đảm bảo unique keys
    const kSurf = [...new Set([...KEYS.SURFACE_AUTO, ...KEYS.SURFACE_MANUAL])];
    const kGeo  = [...new Set([...KEYS.GEO_AUTO, ...KEYS.GEO_MANUAL])];
    const kProp = [...new Set([...KEYS.PROP_AUTO])];
    const kApp  = [...new Set([...KEYS.APP_MANUAL])];

    let cntFull=0, cntGeoProp=0, cntSurfGeo=0, cntSurfProp=0, cntMissing=0;
    let sumSurf={}, sumGeo={}, sumProp={}, sumApp={};
    let nSurf=0, nGeo=0, nProp=0, nApp=0;

    // Reset counter maps
    const initSum = (keys, map) => keys.forEach(k => map[k] = 0);
    initSum(kSurf, sumSurf); initSum(kGeo, sumGeo); initSum(kProp, sumProp); initSum(kApp, sumApp);

    allIds.forEach(id => {
        const s = RADAR_DATA[id];
        const check = (keys) => keys.some(k => (s[k]||0) > 0);
        
        const hasSurf = check(kSurf);
        const hasGeo  = check(kGeo);
        const hasProp = check(kProp);
        const hasApp  = check(kApp);

        if(hasSurf && hasGeo && hasProp) cntFull++;
        else if(!hasSurf && hasGeo && hasProp) cntGeoProp++;
        else if(hasSurf && hasGeo && !hasProp) cntSurfGeo++;
        else if(hasSurf && !hasGeo && hasProp) cntSurfProp++;
        else cntMissing++;

        const addSum = (has, keys, map) => {
            if(has) {
                keys.forEach(k => map[k] += (s[k]||0));
                return 1;
            }
            return 0;
        };
        nSurf += addSum(hasSurf, kSurf, sumSurf);
        nGeo  += addSum(hasGeo,  kGeo,  sumGeo);
        nProp += addSum(hasProp, kProp, sumProp);
        nApp  += addSum(hasApp,  kApp,  sumApp);
    });

    document.getElementById('cntFull').innerText = cntFull;
    document.getElementById('cntGeoProp').innerText = cntGeoProp;
    document.getElementById('cntSurfGeo').innerText = cntSurfGeo;
    document.getElementById('cntSurfProp').innerText = cntSurfProp;
    document.getElementById('cntMissing').innerText = cntMissing;

    // Vẽ biểu đồ trung bình dùng UNIFIED_KEYS để đồng bộ thứ tự
    drawAvgChart('avgSurf', UNIFIED_KEYS.SURFACE, sumSurf, nSurf, 'rgba(239,68,68,1)');
    drawAvgChart('avgGeo',  UNIFIED_KEYS.GEO,     sumGeo,  nGeo,  'rgba(59,130,246,1)');
    drawAvgChart('avgProp', UNIFIED_KEYS.PROP,    sumProp, nProp, 'rgba(16,185,129,1)');
    drawAvgChart('avgApp',  UNIFIED_KEYS.APP,     sumApp,  nApp,  'rgba(147,51,234,1)');

    applyFilters(); 
}

function applyFilters() {
    FULL_PAGE = 1;
    const valSurf = document.getElementById('f_surf').value;
    const valGeo  = document.getElementById('f_geo').value;
    const valProp = document.getElementById('f_prop').value;
    const valApp  = document.getElementById('f_app') ? document.getElementById('f_app').value : 'ALL';
    const search  = document.getElementById('s_full').value.toUpperCase();
    
    CURRENT_VIEW_LIST = ALL_IDS_LIST.filter(id => {
        const s = RADAR_DATA[id] || {};
        // Helper check exist
        const chk = (keys) => keys.some(k => (s[k]||0) > 0);
        
        const hasSurf = chk([...KEYS.SURFACE_AUTO, ...KEYS.SURFACE_MANUAL]);
        const hasGeo  = chk([...KEYS.GEO_AUTO, ...KEYS.GEO_MANUAL]);
        const hasProp = chk(KEYS.PROP_AUTO);
        const hasApp  = chk(KEYS.APP_MANUAL);

        if (valSurf !== 'ALL' && ((valSurf === 'YES') !== hasSurf)) return false;
        if (valGeo  !== 'ALL' && ((valGeo === 'YES')  !== hasGeo))  return false;
        if (valProp !== 'ALL' && ((valProp === 'YES') !== hasProp)) return false;
        if (valApp  !== 'ALL' && ((valApp === 'YES')  !== hasApp))  return false;

        if (search && !id.toUpperCase().includes(search)) return false;
        return true;
    });
    
    document.getElementById('tableTitle').innerText = `DANH SÁCH LỌC (${CURRENT_VIEW_LIST.length} CUỘN)`;
    renderFullTable();
}

/**
 * 4. UI RENDER FUNCTIONS
 */
function renderFullTable() {
    const start = (FULL_PAGE - 1) * 50;
    const items = CURRENT_VIEW_LIST.slice(start, start + 50);
    const tbody = document.getElementById('tbody_full');
    
    tbody.innerHTML = items.map((id, i) => {
        const s = RADAR_DATA[id] || {};
        const chk = (keys) => keys.some(k => (s[k]||0) > 0);
        
        let tags = '';
        if(chk([...KEYS.SURFACE_AUTO, ...KEYS.SURFACE_MANUAL])) tags += '<span class="detail-tag" style="color:#dc2626;border:1px solid #dc2626">Bề mặt</span> ';
        if(chk([...KEYS.GEO_AUTO, ...KEYS.GEO_MANUAL])) tags += '<span class="detail-tag" style="color:#0284c7;border:1px solid #0284c7">Hình học</span> ';
        if(chk(KEYS.PROP_AUTO)) tags += '<span class="detail-tag" style="color:#16a34a;border:1px solid #16a34a">Cơ/Lý</span> ';
        if(chk(KEYS.APP_MANUAL)) tags += '<span class="detail-tag" style="color:#9333ea;border:1px solid #9333ea">Ngoại quan</span> ';

        return `<tr>
            <td>${start + i + 1}</td>
            <td style="font-weight:bold;color:#333">${id}</td>
            <td style="text-align:left;">${tags}</td>
            <td><button class="btn-reset" onclick="showModal('${id}','${id}')" style="background:#0f172a;color:white;border:none;padding:4px 10px;border-radius:4px;">Xem</button></td>
        </tr>`;
    }).join('');
    
    const maxPage = Math.ceil(CURRENT_VIEW_LIST.length / 50) || 1;
    document.getElementById('pinfo_full').innerText = `${FULL_PAGE} / ${maxPage}`;
}

// Hàm vẽ Radar trung bình
function drawAvgChart(canvasId, keys, sums, count, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const data = keys.map(k => count > 0 ? (sums[k] / count).toFixed(2) : 0);
    const labels = keys.map(k => DEFECT_NAMES[k] || k);
    renderMiniRadar(canvasId, Chart.getChart(canvas), labels, data, color);
}

// Hàm vẽ Radar nhỏ (Dùng chung cho Summary, Input Preview, và View Details)
// CẬP NHẬT HÀM: renderMiniRadar
// Thêm tham số: coilId (để tra cứu data gốc), keys (để biết đang hover vào lỗi nào)
function renderMiniRadar(canvasId, chartInstance, labels, data, color, coilId = null, keys = null) {
    if (chartInstance) chartInstance.destroy();
    const ctx = document.getElementById(canvasId).getContext('2d');
    
    return new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Điểm', 
                data: data,
                borderColor: color, 
                backgroundColor: color.replace('1)', '0.2)'),
                borderWidth: 2, 
                pointBackgroundColor: '#fff', 
                pointRadius: 3,
                pointHoverRadius: 6 // Tăng kích thước khi hover để dễ nhìn
            }]
        },
        options: {
            responsive: true, 
            maintainAspectRatio: false,
            scales: { 
                r: { 
                    min: 0, max: 6, 
                    ticks: { display: false, stepSize: 1 }, 
                    pointLabels: { font: { size: 11, weight: 'bold' } } // Chữ to hơn chút
                } 
            },
            plugins: { 
                legend: { display: false },
                // --- CẤU HÌNH TOOLTIP CHI TIẾT ---
                tooltip: {
                    enabled: true, // Bật tooltip
                    callbacks: {
                        label: function(context) {
                            return ` Điểm phân hạng: C${context.raw}`;
                        },
                        // Dòng phụ hiển thị chi tiết dữ liệu thô
                        afterLabel: function(context) {
                            // Chỉ hiển thị nếu có coilId và keys (tức là Radar chi tiết, không phải Radar trung bình)
                            if (coilId && keys) {
                                const index = context.dataIndex;
                                const originalKey = keys[index]; // Lấy key gốc (ví dụ 'MI', 'Crown')
                                const detail = getRawDetailString(coilId, originalKey);
                                return detail ? ` ${detail}` : '';
                            }
                            return '';
                        }
                    },
                    backgroundColor: 'rgba(0, 0, 0, 0.8)',
                    titleFont: { size: 14 },
                    bodyFont: { size: 13 },
                    padding: 10,
                    displayColors: false // Ẩn ô màu trong tooltip cho gọn
                }
            }
        }
    });
}

/**
 * 5. INPUT TAB LOGIC (EDIT MODE)
 */
let INPUT_PAGE = 1; // Trang hiện tại
const INPUT_PAGE_SIZE = 50;
function initInputTab() {
    if(!MANUAL_CONFIG) {
        fetch('/get_manual_config').then(r=>r.json()).then(d => {
            MANUAL_CONFIG = d;
            INPUT_PAGE = 1; // Reset về trang 1 khi mới mở tab
            renderInputList();
        });
    } else {
        // Không reset page ở đây để giữ trạng thái nếu người dùng chuyển tab qua lại
        renderInputList();
    }
}
function renderInputList() {
    const div = document.getElementById('inputListContainer');
    const search = document.getElementById('inputSearch').value.toUpperCase();
    const allIds = Object.keys(RADAR_DATA).sort();
    
    // Lọc dữ liệu
    let filteredIds = allIds.filter(id => id.includes(search));
    
    // Tính toán phân trang
    const totalPages = Math.ceil(filteredIds.length / INPUT_PAGE_SIZE) || 1;
    
    // Đảm bảo trang hiện tại không vượt quá tổng số trang
    if (INPUT_PAGE > totalPages) INPUT_PAGE = totalPages;
    if (INPUT_PAGE < 1) INPUT_PAGE = 1;

    // Cắt dữ liệu theo trang
    const start = (INPUT_PAGE - 1) * INPUT_PAGE_SIZE;
    const displayIds = filteredIds.slice(start, start + INPUT_PAGE_SIZE);
    
    // Render HTML
    div.innerHTML = displayIds.map(id => {
        const isChecked = RADAR_DATA[id]['IS_CHECKED'] ? '✅' : '';
        const activeClass = (CURRENT_INPUT_COIL === id) ? 'active' : '';
        return `<div class="coil-item ${activeClass}" onclick="selectInputCoil('${id}')" id="in_${id}"><span>${id}</span> <span>${isChecked}</span></div>`;
    }).join('');
    
    // Cập nhật thông tin số trang (Footer)
    document.getElementById('inputPageInfo').innerText = `${INPUT_PAGE} / ${totalPages}`;
}
function changeInputPage(delta) {
    const search = document.getElementById('inputSearch').value.toUpperCase();
    const allIds = Object.keys(RADAR_DATA);
    const filteredLength = allIds.filter(id => id.includes(search)).length;
    const maxPage = Math.ceil(filteredLength / INPUT_PAGE_SIZE) || 1;

    const newPage = INPUT_PAGE + delta;
    if (newPage >= 1 && newPage <= maxPage) {
        INPUT_PAGE = newPage;
        renderInputList();
    }
}
// Trong qlcl.js

function selectInputCoil(id) {
    CURRENT_INPUT_COIL = id;
    const coilData = RADAR_DATA[id] || {};

    // Lấy Gốc
    ORIGINAL_SNAPSHOT = coilData['auto_scores'] ? JSON.parse(JSON.stringify(coilData['auto_scores'])) : {};
    
    INPUT_TEMP_DATA = {};
    
    const allDefectKeys = [
        ...UNIFIED_KEYS.SURFACE, ...UNIFIED_KEYS.GEO, 
        ...UNIFIED_KEYS.PROP, ...UNIFIED_KEYS.APP
    ];

    allDefectKeys.forEach(key => {
        // Ưu tiên lấy từ RADAR_DATA (Dữ liệu hiện tại/đã sửa)
        if (coilData.hasOwnProperty(key)) {
            INPUT_TEMP_DATA[key] = coilData[key];
        } else {
            // Fallback về gốc
            INPUT_TEMP_DATA[key] = ORIGINAL_SNAPSHOT[key] || 0;
        }
    });

    // ... (Phần update UI giữ nguyên) ...
    document.querySelectorAll('.coil-item').forEach(e => e.classList.remove('active'));
    document.getElementById(`in_${id}`)?.classList.add('active');
    document.getElementById('inputEmpty').style.display = 'none';
    document.getElementById('radarInputArea').style.display = 'grid'; 
    document.getElementById('lblInputCoil').innerText = id;
    
    drawInteractiveRadars();
}

function resetCurrentInput() {
    if(!CURRENT_INPUT_COIL) return;
    
    if(confirm('Khôi phục về dữ liệu gốc (Máy đo) và LƯU lại?')) {
        // 1. Revert dữ liệu tạm về Gốc (Auto Scores)
        // Nếu không có auto_scores thì coi như cuộn sạch ({})
        INPUT_TEMP_DATA = ORIGINAL_SNAPSHOT ? JSON.parse(JSON.stringify(ORIGINAL_SNAPSHOT)) : {};
        
        // 2. Vẽ lại biểu đồ ngay lập tức
        drawInteractiveRadars();

        // Chuẩn bị danh sách tất cả các loại lỗi
        const allDefectKeys = [
            ...UNIFIED_KEYS.SURFACE, ...UNIFIED_KEYS.GEO, 
            ...UNIFIED_KEYS.PROP, ...UNIFIED_KEYS.APP
        ];

        // 3. Cập nhật biến toàn cục RADAR_DATA (Cập nhật Bộ nhớ Client)
        if(RADAR_DATA[CURRENT_INPUT_COIL]) {
            allDefectKeys.forEach(key => {
                // Lấy giá trị từ bản reset, nếu không có thì ép về 0
                const val = INPUT_TEMP_DATA[key] || 0;
                // Gán trực tiếp vào RADAR_DATA (dạng phẳng)
                RADAR_DATA[CURRENT_INPUT_COIL][key] = val;
            });
            
            RADAR_DATA[CURRENT_INPUT_COIL]['IS_CHECKED'] = true;
        }

        // 4. Gửi dữ liệu xuống Backend (Cập nhật Database)
        const cleanScores = {};
        allDefectKeys.forEach(k => {
            // [SỬA LỖI TẠI ĐÂY]: Chấp nhận số 0
            if (INPUT_TEMP_DATA[k] !== undefined) {
                cleanScores[k] = INPUT_TEMP_DATA[k];
            } else {
                // Nếu key không tồn tại trong bản gốc (VD: lỗi máy không bắt được)
                // Ta phải gửi 0 lên để đè mất lỗi cũ trong DB (nếu có)
                cleanScores[k] = 0;
            }
        });

        showLoading();
        fetch('/save_manual_data', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                coil_id: CURRENT_INPUT_COIL, 
                scores: cleanScores // Gửi object chứa đầy đủ các điểm 0
            })
        }).then(r=>r.json()).then(d => {
            hideLoading();
            
            // 5. Tính toán lại Tab Tổng Hợp
            calculateSummary();
            renderInputList();
            
            alert('Đã khôi phục về gốc thành công!');
        }).catch(e => {
            hideLoading();
            alert('Lỗi khi lưu Reset: ' + e);
        });
    }
}
// Trong file qlcl.js

function saveManualData() {
    if(!CURRENT_INPUT_COIL) return;

    // Chuẩn bị dữ liệu gửi đi
    const cleanScores = {};
    const allDefectKeys = [
        ...UNIFIED_KEYS.SURFACE, ...UNIFIED_KEYS.GEO, 
        ...UNIFIED_KEYS.PROP, ...UNIFIED_KEYS.APP
    ];
    
    allDefectKeys.forEach(k => {
        // Chấp nhận cả số 0
        if(INPUT_TEMP_DATA[k] !== undefined) {
            cleanScores[k] = INPUT_TEMP_DATA[k];
        }
    });

    showLoading();
    fetch('/save_manual_data', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ coil_id: CURRENT_INPUT_COIL, scores: cleanScores, user: 'QC_User' }) 
    }).then(r=>r.json()).then(d => {
        hideLoading();
        alert(d.msg);
        
        // Cập nhật Client (Global State)
        if(RADAR_DATA[CURRENT_INPUT_COIL]) {
            for (const [key, value] of Object.entries(cleanScores)) {
                RADAR_DATA[CURRENT_INPUT_COIL][key] = value;
            }
            RADAR_DATA[CURRENT_INPUT_COIL]['IS_CHECKED'] = true;
        }
        
        renderInputList();
        drawInteractiveRadars();
        calculateSummary(); // Đồng bộ Tab Tổng hợp
    });
}

function drawInteractiveRadars() {
    // Helper lấy dữ liệu: Ưu tiên lấy từ INPUT_TEMP_DATA (đang sửa), nếu không có thì lấy 0
    const getData = (keys) => keys.map(k => INPUT_TEMP_DATA[k] || 0);

    // 1. BỀ MẶT (SURFACE)
    // SỬA: Thay KEYS.SURFACE_MANUAL thành UNIFIED_KEYS.SURFACE để sửa được cả lỗi máy tính
    inputCharts.surf = createClickableRadar(
        'chartInSurf', 
        inputCharts.surf, 
        UNIFIED_KEYS.SURFACE, 
        getData(UNIFIED_KEYS.SURFACE), 
        'rgba(239,68,68,1)', 
        UNIFIED_KEYS.SURFACE // <--- CHO PHÉP SỬA TOÀN BỘ
    );
    attachScrollEvent('chartInSurf', inputCharts.surf, UNIFIED_KEYS.SURFACE);

    // 2. HÌNH HỌC (GEOMETRY)
    // SỬA: Cho phép sửa toàn bộ (bao gồm Độ phẳng, Độ vồng...)
    inputCharts.geo = createClickableRadar(
        'chartInGeo', 
        inputCharts.geo, 
        UNIFIED_KEYS.GEO, 
        getData(UNIFIED_KEYS.GEO), 
        'rgba(59,130,246,1)', 
        UNIFIED_KEYS.GEO // <--- CHO PHÉP SỬA TOÀN BỘ
    );
    attachScrollEvent('chartInGeo', inputCharts.geo, UNIFIED_KEYS.GEO);
    
    // 3. CƠ/LÝ/HÓA (PROP)
    // SỬA: Trước đây để [] (không cho sửa), nay mở ra cho sửa nếu cần thiết
    inputCharts.prop = createClickableRadar(
        'chartInProp', 
        inputCharts.prop, 
        UNIFIED_KEYS.PROP, 
        getData(UNIFIED_KEYS.PROP), 
        'rgba(16,185,129,1)', 
        UNIFIED_KEYS.PROP // <--- CHO PHÉP SỬA TOÀN BỘ
    );
    attachScrollEvent('chartInProp', inputCharts.prop, UNIFIED_KEYS.PROP);
    
    // 4. NGOẠI QUAN (APP)
    inputCharts.app = createClickableRadar(
        'chartInApp', 
        inputCharts.app, 
        UNIFIED_KEYS.APP, 
        getData(UNIFIED_KEYS.APP), 
        'rgba(147,51,234,1)', 
        UNIFIED_KEYS.APP // <--- CHO PHÉP SỬA TOÀN BỘ
    );
    attachScrollEvent('chartInApp', inputCharts.app, UNIFIED_KEYS.APP);
}

// Hàm tạo Radar tương tác (Click + Scroll + RightClick)
// Biến toàn cục để theo dõi đang sửa lỗi nào
let CURRENT_EDIT_KEY = null; 
let CURRENT_EDIT_CHART = null;

// Hàm tạo Radar tương tác (Click Label -> Hiện Popup, Hiển thị 2 Dataset)
// Hàm tạo Radar tương tác (Giao diện High Contrast)
function createClickableRadar(canvasId, oldChart, keys, currentData, color, editableKeys) {
    if (oldChart) oldChart.destroy();
    const cvs = document.getElementById(canvasId);
    const ctx = cvs.getContext('2d');
    const labels = keys.map(k => DEFECT_NAMES[k] || k);

    // Lấy dữ liệu gốc
    const originalData = keys.map(k => ORIGINAL_SNAPSHOT[k] || 0);

    const chart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [
                {
                    // --- DỮ LIỆU ĐANG SỬA (Lớp trên) ---
                    label: 'Đang sửa',
                    data: currentData,
                    borderColor: color,           // Màu chính (Đỏ/Xanh/...)
                    backgroundColor: color.replace('1)', '0.15)'), // Màu nền nhẹ
                    borderWidth: 3,               // Nét dày hơn
                    borderDash: [8, 6],           // Nét đứt thưa, rõ ràng
                    
                    // Style cho điểm (Point)
                    pointBackgroundColor: 'white', // Điểm rỗng (nền trắng)
                    pointBorderColor: color,
                    pointBorderWidth: 2,
                    pointHoverRadius: 8,
                    
                    // Logic: Điểm nào KHÁC gốc thì to lên, giống gốc thì nhỏ
                    pointRadius: (ctx) => {
                        const index = ctx.dataIndex;
                        const key = keys[index];
                        const val = INPUT_TEMP_DATA[key] || 0;
                        const oldVal = ORIGINAL_SNAPSHOT[key] || 0;
                        return (val != oldVal) ? 6 : 4; // Khác: 6px, Giống: 4px
                    },
                    // Logic: Điểm nào KHÁC gốc thì viền đỏ rực
                    pointBorderColor: (ctx) => {
                         const index = ctx.dataIndex;
                         const key = keys[index];
                         const val = INPUT_TEMP_DATA[key] || 0;
                         const oldVal = ORIGINAL_SNAPSHOT[key] || 0;
                         return (val != oldVal) ? '#dc2626' : color; 
                    },
                    order: 1 // Vẽ đè lên trên
                },
                {
                    // --- DỮ LIỆU GỐC (Lớp dưới làm nền) ---
                    label: 'Gốc',
                    data: originalData,
                    borderColor: '#64748b',       // Xám đậm
                    backgroundColor: 'rgba(148, 163, 184, 0.2)', // Nền xám nhạt (quan trọng để thấy sự chênh lệch)
                    borderWidth: 2,
                    pointRadius: 0,               // Ẩn điểm gốc cho đỡ rối mắt
                    pointHoverRadius: 0,
                    borderDash: [],               // Nét liền
                    order: 2
                }
            ]
        },
        options: {
            events: ['click', 'mousemove'], 
            responsive: true, maintainAspectRatio: false, animation: false,
            scales: {
                r: {
                    min: 0, max: 6, 
                    ticks: { display: false, stepSize: 1 },
                    grid: { color: '#e2e8f0' }, // Màu lưới nhạt
                    angleLines: { color: '#e2e8f0' },
                    pointLabels: {
                        font: { size: 11, weight: 'bold' },
                        // Tô đỏ Label nếu giá trị tại đó bị thay đổi
                        color: (c) => {
                            const key = keys[c.index];
                            const isChanged = INPUT_TEMP_DATA[key] != ORIGINAL_SNAPSHOT[key];
                            return isChanged ? '#dc2626' : '#64748b'; 
                        },
                        // Thêm dấu * vào label nếu thay đổi
                        callback: (label, index) => {
                             const key = keys[index];
                             const isChanged = INPUT_TEMP_DATA[key] != ORIGINAL_SNAPSHOT[key];
                             return isChanged ? `${label} (*)` : label;
                        }
                    }
                }
            },
            plugins: { 
                legend: { 
                    display: true, 
                    position: 'top',
                    labels: { usePointStyle: true, boxWidth: 8 } 
                }, 
                tooltip: { enabled: false } 
            },
            
            // XỬ LÝ CLICK (Giữ nguyên logic cũ)
            onClick: (e, activeElements, chart) => {
                const pos = Chart.helpers.getRelativePosition(e, chart);
                const idx = getIndexFromAngle(pos, chart, keys.length);
                if (idx !== -1 && editableKeys.includes(keys[idx])) {
                    const key = keys[idx];
                    openScorePopup(e.native, key, INPUT_TEMP_DATA[key]||0, DEFECT_NAMES[key]||key, chart);
                }
            }
        }
    });

    return chart;
}

// Hàm phụ trợ tính góc để biết click vào lỗi nào (đã có trong code cũ nhưng tách ra cho gọn)
function getIndexFromAngle(position, chart, totalKeys) {
    const rScale = chart.scales.r;
    const dx = position.x - rScale.xCenter;
    const dy = position.y - rScale.yCenter;
    let angle = Math.atan2(dy, dx);
    // Chuẩn hóa góc về hệ Chart.js (Bắt đầu từ 12h)
    if (angle < -Math.PI/2) angle += 2*Math.PI;
    angle += Math.PI/2; 
    
    const anglePerSlice = (2 * Math.PI) / totalKeys;
    let index = Math.floor((angle + anglePerSlice/2) / anglePerSlice);
    if (index >= totalKeys) index = 0;
    return index;
}

// --- LOGIC POPUP ---

function openScorePopup(event, key, currentValue, labelName, chartInstance) {
    CURRENT_EDIT_KEY = key;
    CURRENT_EDIT_CHART = chartInstance;
    
    const popup = document.getElementById('scoreInputPopup');
    document.getElementById('popupTitle').innerText = labelName;
    document.getElementById('manualScoreInput').value = currentValue;
    
    // Position popup ngay tại chuột
    popup.style.left = event.pageX + 'px';
    popup.style.top = event.pageY + 'px';
    popup.style.display = 'block';
    
    // Focus vào ô input
    document.getElementById('manualScoreInput').focus();
}

function closePopup() {
    document.getElementById('scoreInputPopup').style.display = 'none';
    CURRENT_EDIT_KEY = null;
}

function setPopupScore(val) {
    document.getElementById('manualScoreInput').value = val;
    confirmPopupScore(); // Chọn nhanh thì lưu luôn cho tiện
}

function confirmPopupScore() {
    if (!CURRENT_EDIT_KEY) return;
    
    const val = parseFloat(document.getElementById('manualScoreInput').value);
    
    // Cập nhật dữ liệu tạm
    INPUT_TEMP_DATA[CURRENT_EDIT_KEY] = val;
    
    // Update Chart ngay lập tức (Chỉ update dataset 0 - Nét đứt)
    if (CURRENT_EDIT_CHART) {
        // Tìm index của key trong chart labels
        const labels = CURRENT_EDIT_CHART.data.labels;

        // Cập nhật mảng data của dataset[0]
        const dataArr = CURRENT_EDIT_CHART.data.datasets[0].data;
    }
    drawInteractiveRadars(); 
    closePopup();
}

// Click ra ngoài thì đóng popup
document.addEventListener('click', function(event) {
    const popup = document.getElementById('scoreInputPopup');
    const isClickInside = popup.contains(event.target);
    // Cần check thêm click vào canvas không (đã xử lý trong onClick chart)
    // Code này chỉ để đóng nếu click ra vùng trống
    if (!isClickInside && event.target.tagName !== 'CANVAS' && popup.style.display === 'block') {
         // Kiểm tra xem có phải đang click vào nút mở popup ko (đã handled)
         // Tạm thời bỏ qua auto-close click outside để tránh xung đột với click canvas
    }
});
function handleRadarHover(position, chart, keys, canvasId) {
    const rScale = chart.scales.r;
    const dx = position.x - rScale.xCenter, dy = position.y - rScale.yCenter;
    const dist = Math.sqrt(dx*dx + dy*dy);
    let angle = Math.atan2(dy, dx);
    if (angle < -Math.PI/2) angle += 2*Math.PI; angle += Math.PI/2; if (angle < 0) angle += 2*Math.PI;
    
    const anglePerSlice = (2 * Math.PI) / keys.length;
    let index = Math.floor((angle + anglePerSlice/2) / anglePerSlice);
    if (index >= keys.length) index = 0;

    const maxDist = rScale.getDistanceFromCenterForValue(6);
    let snapVal = Math.round((dist / maxDist) * 6);
    if (snapVal > 6) snapVal = 6; if (snapVal < 0) snapVal = 0;

    if (hoverState.index !== index || hoverState.value !== snapVal || hoverState.chartId !== canvasId) {
        hoverState = { chartId: canvasId, index: index, value: snapVal };
        chart.update();
    }
}

function attachScrollEvent(canvasId, chartInstance, keys) {
    const cvs = document.getElementById(canvasId);
    cvs.onwheel = (e) => {
        if (!CURRENT_INPUT_COIL) return;
        e.preventDefault();
        if (hoverState.chartId === canvasId && hoverState.index !== -1) {
            const key = keys[hoverState.index];
            let val = INPUT_TEMP_DATA[key] || 0;
            if (e.deltaY < 0) val = Math.min(6, val + 1); else val = Math.max(0, val - 1);
            INPUT_TEMP_DATA[key] = val;
            chartInstance.data.datasets[0].data[hoverState.index] = val;
            chartInstance.update();
            hoverState.value = val;
        }
    };
}

/**
 * 6. NAVIGATION & MODAL LOGIC
 */
function switchGroup(groupName) {
    document.querySelectorAll('.group-btn').forEach(b => b.classList.remove('active'));
    const btnMap = {'SUMMARY':'.g-sum', 'SURFACE':'.g-surf', 'GEOMETRY':'.g-geo', 'PROP':'.g-prop', 'INPUT':'.g-input'};
    if(btnMap[groupName]) document.querySelector(btnMap[groupName]).classList.add('active');
    document.querySelectorAll('.sub-group').forEach(div => div.classList.remove('show'));
    
    if(groupName === 'INPUT') {
        openTab(null, 'INPUT_TAB');
        initInputTab();
    } else {
        document.getElementById(`grp_${groupName}`).classList.add('show');
        if(groupName === 'SUMMARY') openTab(null, 'SUMMARY_TAB');
        else { const first = document.querySelector(`#grp_${groupName} .tab-btn`); if(first) first.click(); }
    }
}

function openTab(evt, name) {
    document.querySelectorAll('.tab-content').forEach(e => e.style.display = 'none');
    document.querySelectorAll('.tab-btn').forEach(e => e.classList.remove('active'));
    document.getElementById(name).style.display = 'block';
    if (evt) evt.currentTarget.classList.add('active');
    if (name !== 'SUMMARY_TAB' && name !== 'INPUT_TAB') renderTabList(name);
}

function renderTabList(name) {
    const search = document.getElementById(`s_${name}`)?.value.toUpperCase() || '';
    const filter = document.getElementById(`f_${name}`)?.value || 'all';
    let list = TABLE_DATA[name] || [];
    
    list = list.filter(item => {
        return item['Cuộn'].toString().toUpperCase().includes(search) && 
               (filter === 'all' || item['Loại'] === filter);
    });

    TAB_PAGING[name].data = list;
    TAB_PAGING[name].page = 1;
    drawTable(name);
}

function drawTable(name) {
    const conf = TAB_PAGING[name];
    const start = (conf.page - 1) * PAGE_SIZE;
    const items = conf.data.slice(start, start + PAGE_SIZE);
    
    document.getElementById(`tbody_${name}`).innerHTML = items.map((r, i) => {
        // --- [LOGIC MỚI] ---
        // Tra cứu Mác thép từ biến RADAR_DATA bằng ID cuộn (r['Cuộn'])
        const coilId = r['Cuộn'];
        const grade = (RADAR_DATA[coilId] && RADAR_DATA[coilId].GRADE) ? RADAR_DATA[coilId].GRADE : '---';
        // -------------------

        return `<tr>
            <td><b>${start + i + 1}</b></td>
            <td style="font-weight:600">${coilId}</td>
            
            <td><span style="font-size:0.9em; color:#475569; background:#f1f5f9; padding:2px 6px; border-radius:4px;">${grade}</span></td>
            
            <td><span class="badge type-${r['Loại']}">${r['Loại']}</span></td>
            <td style="text-align:left; max-width: 450px;">
                <div style="display:flex; flex-wrap:wrap; gap:4px;">
                    ${Object.entries(r['DetailCounts']).map(([k,v]) => 
                        `<span style="display:inline-block; background:#f8fafc; border:1px solid #cbd5e1; border-radius:4px; padding:2px 6px; font-size:0.85em; color:#475569; white-space:nowrap;">
                            ${k}: <span style="font-weight:700; color:#0f172a;">${v}</span>
                        </span>`
                    ).join('')}
                </div>
            </td>
        </tr>`;
    }).join('');
    
    document.getElementById(`pinfo_${name}`).innerText = `${start + 1}-${Math.min(start + PAGE_SIZE, conf.data.length)} / ${conf.data.length}`;
}
function changeTabPage(name, d) {
    const conf = TAB_PAGING[name];
    if(conf.page+d >= 1 && conf.page+d <= Math.ceil(conf.data.length/PAGE_SIZE)) { conf.page += d; drawTable(name); }
}
// Trong file qlcl.js hoặc thẻ <script> cuối qlcl.html

function triggerBatchSync() {
    const rawIds = document.getElementById('txtBatchCoils').value.trim();
    
    if (!rawIds) {
        alert("⚠️ Vui lòng nhập danh sách ID cuộn!");
        return;
    }

    // 1. LẤY MÁC THÉP ĐANG CHỌN (Nếu cần gửi kèm để update lại mác)
    const currentGrade = document.getElementById('globalGradeSelect') ? document.getElementById('globalGradeSelect').value : 'SAE1006'; 

    // Hiển thị loading
    showLoading(); 
    // Sửa text loading cho người dùng biết
    const overlay = document.getElementById('loadingOverlay');
    if(overlay) overlay.querySelector('h3').innerText = "Đang gửi lệnh quét Batch...";

    fetch('/api/sync_batch_coils', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            coil_ids: rawIds,
            grade: currentGrade 
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.status === 'success') {
            // Thông báo thành công và xóa ô nhập
            alert(`✅ ${data.msg}`);
            document.getElementById('txtBatchCoils').value = ''; 
            // Không reload ngay vì chạy ngầm, người dùng tự reload sau
        } else {
            alert(`❌ Lỗi: ${data.msg}`);
        }
    })
    .catch(err => {
        hideLoading();
        alert("❌ Lỗi kết nối Server: " + err);
    });
}
// Modal Xem Chi Tiết
function showModal(str, title) {
    document.getElementById('modalTitle').innerText = title;
    document.getElementById('modalSearch').value = '';
    MODAL_ALL = str.includes(',') ? str.split(',').map(s=>s.trim()).filter(x=>x) : [str.trim()];
    MODAL_FILT = MODAL_ALL; MODAL_PAGE = 1;
    document.getElementById('detailModal').style.display = 'flex';
    if(MODAL_ALL.length === 1 && MODAL_ALL[0]) { renderModalList(); selectCoil(MODAL_ALL[0]); }
    else { document.getElementById('emptyView').style.display = 'flex'; document.getElementById('radarView').style.display = 'none'; renderModalList(); }
}
function closeModal(){ document.getElementById('detailModal').style.display='none'; }
function filterModalList(){ MODAL_FILT=MODAL_ALL.filter(c=>c.toUpperCase().includes(document.getElementById('modalSearch').value.toUpperCase())); MODAL_PAGE=1; renderModalList(); }
function changeModalPage(d){ if(MODAL_PAGE+d >=1 && MODAL_PAGE+d <= Math.ceil(MODAL_FILT.length/50)) { MODAL_PAGE+=d; renderModalList(); } }
function renderModalList(){
    const start=(MODAL_PAGE-1)*50;
    document.getElementById('modalList').innerHTML = MODAL_FILT.slice(start,start+50).map(c=>`<div class="coil-item" id="c_${c}" onclick="selectCoil('${c}')"><span>${c}</span> <small>▶</small></div>`).join('');
    document.getElementById('modalPageInfo').innerText=`${MODAL_PAGE}/${Math.ceil(MODAL_FILT.length/50)}`;
}
function selectCoil(id){
    document.querySelectorAll('.coil-item').forEach(e=>e.classList.remove('active'));
    document.getElementById(`c_${id}`)?.classList.add('active');
    document.getElementById('emptyView').style.display='none';
    document.getElementById('radarView').style.display='flex';
    setTimeout(() => drawCoilRadar(id), 50);
}
function drawCoilRadar(id){
    const s = RADAR_DATA[id] || {};
    // Hàm get data cũ
    const getData = (keys) => ({ 
        labels: keys.map(k=>DEFECT_NAMES[k]||k), 
        data: keys.map(k=>s[k]||0),
        keys: keys // Trả về thêm keys gốc để truyền vào chart
    });
    
    const dSurf = getData(UNIFIED_KEYS.SURFACE);
    const dGeo  = getData(UNIFIED_KEYS.GEO);
    const dProp = getData(UNIFIED_KEYS.PROP);
    const dApp  = getData(UNIFIED_KEYS.APP);

    // Truyền thêm id và keys vào hàm render
    mc1 = renderMiniRadar('chartModalSurf', mc1, dSurf.labels, dSurf.data, 'rgba(239,68,68,1)',   id, dSurf.keys);
    mc2 = renderMiniRadar('chartModalGeo',  mc2, dGeo.labels,  dGeo.data,  'rgba(59,130,246,1)',   id, dGeo.keys);
    mc3 = renderMiniRadar('chartModalProp', mc3, dProp.labels, dProp.data, 'rgba(16,185,129,1)',   id, dProp.keys);
    mc4 = renderMiniRadar('chartModalApp',  mc4, dApp.labels,  dApp.data,  'rgba(147,51,234,1)',   id, dApp.keys);
}

// Utils (Upload, Delete...)
function showLoading(){document.getElementById('loadingOverlay').style.display='flex'}
function hideLoading(){document.getElementById('loadingOverlay').style.display='none'}
function resetFilters() { document.getElementById('f_surf').value='ALL'; document.getElementById('f_geo').value='ALL'; document.getElementById('f_prop').value='ALL'; if(document.getElementById('f_app')) document.getElementById('f_app').value='ALL'; document.getElementById('s_full').value=''; applyFilters(); }
function filterSummaryTable(type) {
    resetFilters();
    const setF = (s,g,p) => { document.getElementById('f_surf').value=s; document.getElementById('f_geo').value=g; document.getElementById('f_prop').value=p; };
    if(type==='FULL') setF('YES','YES','YES'); else if(type==='GEO_PROP') setF('NO','YES','YES');
    else if(type==='SURF_GEO') setF('YES','YES','NO'); else if(type==='SURF_PROP') setF('YES','NO','YES');
    applyFilters();
}
// Thêm vào đầu file hoặc trong window.addEventListener('load', ...)
// --- HÀM MỚI: LẤY CHI TIẾT DỮ LIỆU THÔ CHO TOOLTIP ---
function getRawDetailString(coilId, key) {
    if (!coilId || !RADAR_DATA[coilId] || !RADAR_DATA[coilId].raw_data) return null;
    
    const val = RADAR_DATA[coilId].raw_data[key];

    // 1. Nếu là Lỗi Bề Mặt (Dạng danh sách kích thước)
    if (Array.isArray(val)) {
        if (val.length === 0) return "Sạch (0 lỗi)";
        // Hiển thị số lượng và liệt kê vài kích thước đầu
        const count = val.length;
        // Lấy 5 lỗi lớn nhất để hiển thị cho gọn
        const sorted = [...val].sort((a,b) => b-a); 
        const displayStr = sorted.slice(0, 5).join(", ");
        return `SL: ${count} | Size: ${displayStr}${count > 5 ? '...' : ''}`;
    }
    
    // 2. Nếu là Hình học / Cơ tính (Dạng số thực)
    if (typeof val === 'number') {
        // Làm tròn 3 số thập phân cho đẹp
        return `Thực tế: ${val.toFixed(3)}`;
    }

    return null;
}
async function loadGradeList() {
    try {
        const res = await fetch('/api/grade_configs');
        const configs = await res.json();
        const grades = Object.keys(configs);

        const select = document.getElementById('globalGradeSelect');
        if(!select) return;

        const currentVal = select.getAttribute('data-current') || 'SAE1006'; 
        
        select.innerHTML = '';

        // --- [THÊM ĐOẠN NÀY] ---
        // Thêm option ALL lên đầu
        const optAll = document.createElement('option');
        optAll.value = 'ALL';
        optAll.innerText = '-- Tất cả --';
        if(currentVal === 'ALL') optAll.selected = true;
        select.appendChild(optAll);
        // -----------------------

        grades.forEach(g => {
            const opt = document.createElement('option');
            opt.value = g;
            opt.innerText = g;
            if(g === currentVal) opt.selected = true;
            select.appendChild(opt);
        });
    } catch(err) {
        console.error("Lỗi tải danh sách Mác thép:", err);
    }
}

function changeGlobalGrade() {
    const val = document.getElementById('globalGradeSelect').value;
    // Reload trang với tham số grade mới
    window.location.search = `?grade=${val}`;
}
// --- JAVASCRIPT XỬ LÝ QUÉT LIVE ---
function triggerLiveSync() {
    const coilId = document.getElementById('txtLiveCoilId').value.trim();
    
    // 1. LẤY MÁC THÉP ĐANG CHỌN
    const currentGrade = document.getElementById('globalGradeSelect').value; 

    if (!coilId) {
        alert("⚠️ Vui lòng nhập Mã cuộn (ID)!");
        return;
    }

    // Hiển thị loading
    const overlay = document.getElementById('loadingOverlay');
    if(overlay) {
        overlay.style.display = 'flex';
        // Hiển thị rõ đang quét theo mác nào để bạn dễ kiểm tra
        overlay.querySelector('h3').innerText = `Đang quét cuộn ${coilId} (Mác: ${currentGrade})...`;
    }

    fetch('/api/sync_single_coil', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            coil_id: coilId,
            grade: currentGrade // 2. GỬI KÈM MÁC THÉP LÊN SERVER
        })
    })
    .then(response => response.json())
    .then(data => {
        if(overlay) overlay.style.display = 'none';
        
        if (data.status === 'success') {
            alert(`✅ ${data.msg}`);
            location.reload(); 
        } else {
            alert(`❌ Lỗi: ${data.msg}`);
        }
    })
    .catch(err => {
        if(overlay) overlay.style.display = 'none';
        alert("❌ Lỗi kết nối Server: " + err);
    });
}
// Gọi hàm này khi trang load
window.addEventListener('load', () => {
    const urlParams = new URLSearchParams(window.location.search);
    const gradeFromUrl = urlParams.get('grade');
    if(gradeFromUrl) {
        const select = document.getElementById('globalGradeSelect');
        if(select) {
            select.setAttribute('data-current', gradeFromUrl);
            select.value = gradeFromUrl;
        }
    }

    loadGradeList();
});
function changeFullPage(d) { const max = Math.ceil(CURRENT_VIEW_LIST.length/50); if(FULL_PAGE+d>=1 && FULL_PAGE+d<=max) { FULL_PAGE+=d; renderFullTable(); } }
function upAjax(u,i){ const f=document.getElementById(i).files[0]; if(!f)return alert('Chọn file!'); const fd=new FormData(); fd.append('file',f); showLoading(); fetch(u,{method:'POST',body:fd}).then(r=>r.json()).then(d=>{alert(d.msg);location.reload()}).catch(e=>{hideLoading();alert('Lỗi:'+e)}); }
function deleteData(cat){ if(confirm('Xóa dữ liệu?')) { showLoading(); fetch('/delete_data_category',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category:cat})}).then(r=>r.json()).then(d=>{alert(d.msg);location.reload()}).catch(e=>alert(e)); }}
function delCfg(e,n){e.stopPropagation();if(confirm('Xóa?'))fetch('/delete_config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})}).then(()=>location.reload())}