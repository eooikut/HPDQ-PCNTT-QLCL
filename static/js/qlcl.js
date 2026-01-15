/**
 * 1. CONSTANTS & CONFIGURATION
 * Định nghĩa các hằng số dùng chung toàn hệ thống
 */
const KEYS = {
    SURFACE_AUTO: ['MI', 'HPrScale', 'EL', 'HOLE', 'RIP', 'BRUS', 'LC', 'SCRT'],
    SURFACE_MANUAL: ['oil', 'rust', 'scratch_m', 'dirt', 'mark', 'scale', 'other_s', 'gianbien'],
    GEO_AUTO: ['Flatness', 'Crown', 'Wedge', 'ThickDiff', 'WidthDiff'],
    GEO_MANUAL: ['telescope'],

    MECH_AUTO: ['YieldPoint', 'Tensile', 'Elongation', 'Hardness'],
    CHEM_AUTO: ['C', 'Mn', 'Si', 'P', 'S'],
    
    APP_MANUAL: ['strap', 'label_tag', 'packaging', 'edge_cond', 'coil_shape']
};

// Thứ tự hiển thị thống nhất trên mọi biểu đồ
const UNIFIED_KEYS = {
    SURFACE: [...KEYS.SURFACE_MANUAL, ...KEYS.SURFACE_AUTO],
    GEO:     [...KEYS.GEO_MANUAL,     ...KEYS.GEO_AUTO],
    PROP:    [...KEYS.MECH_AUTO,      ...KEYS.CHEM_AUTO],
    APP:     [...KEYS.APP_MANUAL]
};
const REAL_MECHANICAL_KEYS = ['YieldPoint', 'Tensile', 'Elongation', 'Hardness'];
const DEFECT_NAMES = {
    'MI': 'Ngậm xỉ đúc', 
    'HPrScale': 'Xỉ sơ cấp HP', 
    'EL': ' Lỗi xếp lớp',
    'HOLE': 'Lỗ thủng', 
    'RIP': 'Rách bề mặt', 
    'BRUS': 'Vết Hằn trục',
    'LC': 'Nứt dọc', 
    'SCRT': 'Xước bề mặt',
    'oil': 'Gấp nếp', 
    'rust': 'Nếp Nhăn', 
    'scratch_m': 'Vết hằn Pinch Roll',
    'dirt': 'Gãy mặt', 
    'mark': 'Xỉ thứ cấp', 
    'scale': 'Xỉ cán', 
    'other_s': 'Xỉ muối tiêu',
    'gianbien': 'Giãn biên',
    'Flatness': 'Độ phẳng', 
    'Crown': 'Độ vồng', 
    'Wedge': 'Độ nêm',
    'ThickDiff': 'Sai lệch dày', 
    'WidthDiff': 'Sai lệch rộng',
    'telescope': 'Cong cạnh',
    'YieldPoint': 'GH Chảy', 
    'Tensile': 'GH Bền', 
    'Elongation': 'Độ giãn',
    'Hardness': 'Độ cứng', 
    'C': 'Carbon', 
    'Mn': 'Mangan', 
    'Si': 'Silic', 
    'P': 'Photpho', 
    'S': 'Lưu huỳnh',
    'strap': 'Khuyết biên', 
    'label_tag': 'Bava biên', 
    'packaging': 'Vỡ biên',
    'edge_cond': 'Sổ vòng', 
    'coil_shape': 'Loa cuộn'
};

const PAGE_SIZE = 50;


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
function parseDateRobust(dateStr) {
    if (!dateStr) return 0;
    const nums = String(dateStr).match(/\d+/g);
    if (!nums || nums.length < 3) return 0;

    let y, m, d;
    // 2. Tự động nhận diện định dạng:
    // - Nếu số đầu > 31 (VD: 2026) -> Định dạng Quốc tế (Năm-Tháng-Ngày)
    if (parseInt(nums[0]) > 31) {
        y = parseInt(nums[0]);
        m = parseInt(nums[1]) - 1; // Tháng trong JS bắt đầu từ 0 (0 = Tháng 1)
        d = parseInt(nums[2]);
    } 
    // - Nếu số đầu <= 31 (VD: 05) -> Định dạng Việt Nam (Ngày/Tháng/Năm)
    else {
        d = parseInt(nums[0]);
        m = parseInt(nums[1]) - 1;
        y = parseInt(nums[2]);
    }

    // 3. Lấy Giờ, Phút, Giây (nếu có), mặc định là 0
    const h   = parseInt(nums[3] || 0);
    const min = parseInt(nums[4] || 0);
    const sec = parseInt(nums[5] || 0);

    return new Date(y, m, d, h, min, sec).getTime();
}
function calculateSummary() {
    let allIds = Object.keys(RADAR_DATA);

    // --- BƯỚC 1: TỐI ƯU HÓA HIỆU NĂNG (PRE-CALCULATE) ---
    // Tạo một map tạm lưu timestamp để không phải parse lại nhiều lần khi sort
    const dateCache = {};
    
    // Chỉ chạy parseDateRobust đúng 1 lần cho mỗi ID (O(N))
    allIds.forEach(id => {
        dateCache[id] = parseDateRobust(RADAR_DATA[id].production_date || '');
    });

    // --- BƯỚC 2: SẮP XẾP DỰA TRÊN CACHE ---
    // Lúc này việc so sánh cực nhanh vì chỉ là trừ 2 số nguyên (O(N log N))
    allIds.sort((a, b) => {
        const valA = dateCache[a];
        const valB = dateCache[b];
        
        // So sánh thời gian (Giảm dần)
        if (valB !== valA) {
            return valB - valA; 
        }
        // So sánh ID nếu trùng thời gian
        return b.localeCompare(a, undefined, { numeric: true });
    });

    ALL_IDS_LIST = allIds;
    document.getElementById('totalCoils').innerText = allIds.length;

    // --- BƯỚC 3: TÍNH TOÁN THỐNG KÊ (GIỮ NGUYÊN LOGIC CŨ) ---
    const kSurf = [...new Set([...KEYS.SURFACE_AUTO, ...KEYS.SURFACE_MANUAL])];
    const kGeo  = [...new Set([...KEYS.GEO_AUTO, ...KEYS.GEO_MANUAL])];
    
    // Tách riêng Cơ tính và Hóa học (Logic mới đã sửa ở câu trước)
    const kMech = [...new Set(KEYS.MECH_AUTO)]; 
    const kChem = [...new Set(KEYS.CHEM_AUTO)]; 
    const kApp  = [...new Set(KEYS.APP_MANUAL)];
    const kPropChart = [...new Set([...KEYS.MECH_AUTO, ...KEYS.CHEM_AUTO])];

    let cntFull=0, cntGeoProp=0, cntSurfGeo=0, cntSurfProp=0, cntMissing=0;
    let sumSurf={}, sumGeo={}, sumProp={}, sumApp={};
    let nSurf=0, nGeo=0, nProp=0, nApp=0;

    const initSum = (keys, map) => keys.forEach(k => map[k] = 0);
    initSum(kSurf, sumSurf); 
    initSum(kGeo, sumGeo); 
    initSum(kPropChart, sumProp); 
    initSum(kApp, sumApp);

    // Duyệt qua danh sách để đếm
    allIds.forEach(id => {
        const s = RADAR_DATA[id];
        // Hàm check tối ưu hơn chút bằng cách kiểm tra length trước
        const check = (keys) => {
            for (let i = 0; i < keys.length; i++) {
                if ((s[keys[i]] || 0) > 0) return true;
            }
            return false;
        };
        
        const hasSurf = check(kSurf);
        const hasGeo  = check(kGeo);
        const hasMech = check(kMech); 
        const hasChem = check(kChem); 
        const hasApp  = check(kApp);

        // Phân loại
        if(hasSurf && hasGeo && hasMech) cntFull++;
        else if(!hasSurf && hasGeo && hasChem) cntGeoProp++;
        else if(hasSurf && hasGeo && !hasMech) cntSurfGeo++;
        else if(hasSurf && !hasGeo && hasChem) cntSurfProp++;
        else cntMissing++;

        // Cộng dồn để vẽ biểu đồ
        const addSum = (has, keys, map) => {
            if(has) {
                keys.forEach(k => map[k] += (s[k]||0));
                return 1;
            }
            return 0;
        };
        
        nSurf += addSum(hasSurf, kSurf, sumSurf);
        nGeo  += addSum(hasGeo,  kGeo,  sumGeo);
        nProp += addSum(hasMech || hasChem, kPropChart, sumProp);
        nApp  += addSum(hasApp,  kApp,  sumApp);
    });

    // Update UI
    document.getElementById('cntFull').innerText = cntFull;
    document.getElementById('cntGeoProp').innerText = cntGeoProp;
    document.getElementById('cntSurfGeo').innerText = cntSurfGeo;
    document.getElementById('cntSurfProp').innerText = cntSurfProp;
    document.getElementById('cntMissing').innerText = cntMissing;

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
    
    // [SỬA]: Lấy giá trị 2 bộ lọc mới
    const valChem = document.getElementById('f_chem').value;
    const valMech = document.getElementById('f_mech').value;
    
    const valApp  = document.getElementById('f_app') ? document.getElementById('f_app').value : 'ALL';
    const search  = document.getElementById('s_full').value.toUpperCase();
    
    CURRENT_VIEW_LIST = ALL_IDS_LIST.filter(id => {
        const s = RADAR_DATA[id] || {};
        const chk = (keys) => keys.some(k => (s[k]||0) > 0);
        
        const hasSurf = chk([...KEYS.SURFACE_AUTO, ...KEYS.SURFACE_MANUAL]);
        const hasGeo  = chk([...KEYS.GEO_AUTO, ...KEYS.GEO_MANUAL]);
        
        const hasChem = chk(KEYS.CHEM_AUTO);
        const hasMech = chk(KEYS.MECH_AUTO);
        
        const hasApp  = chk(KEYS.APP_MANUAL);

        if (valSurf !== 'ALL' && ((valSurf === 'YES') !== hasSurf)) return false;
        if (valGeo  !== 'ALL' && ((valGeo === 'YES')  !== hasGeo))  return false;
        
        // [SỬA]: Logic lọc riêng
        if (valChem !== 'ALL' && ((valChem === 'YES') !== hasChem)) return false;
        if (valMech !== 'ALL' && ((valMech === 'YES') !== hasMech)) return false;
        
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
        const grade = s['GRADE'] || '---';
        const chk = (keys) => keys.some(k => (s[k]||0) > 0);
        let tags = '';
        
        if(chk([...KEYS.SURFACE_AUTO, ...KEYS.SURFACE_MANUAL])) tags += '<span class="detail-tag" style="color:#dc2626;border:1px solid #dc2626">Bề mặt</span> ';
        if(chk([...KEYS.GEO_AUTO, ...KEYS.GEO_MANUAL])) tags += '<span class="detail-tag" style="color:#0284c7;border:1px solid #0284c7">Hình học</span> ';

        if(chk(KEYS.CHEM_AUTO)) tags += '<span class="detail-tag" style="color:#d97706;border:1px solid #d97706">Hóa học</span> '; // Màu cam
        if(chk(KEYS.MECH_AUTO)) tags += '<span class="detail-tag" style="color:#16a34a;border:1px solid #16a34a">Cơ tính</span> '; // Màu xanh lá
        
        if(chk(KEYS.APP_MANUAL)) tags += '<span class="detail-tag" style="color:#9333ea;border:1px solid #9333ea">Ngoại quan</span> ';

        return `<tr>
            <td>${start + i + 1}</td>                                      <td style="font-weight:bold;color:#333">${id}</td>              <td><span style="font-weight:600; color:#475569; background:#f1f5f9; padding:2px 8px; border-radius:4px;">${grade}</span></td>
            
            <td style="text-align:center;">
                <button class="btn-reset" onclick="showModal('${id}','${id}')" style="background:#0f172a;color:white;border:none;padding:4px 10px;border-radius:4px; cursor:pointer;">
                    Xem
                </button>
            </td>

            <td style="text-align:left;">${tags}</td>
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

// Hàm lấy chuỗi chi tiết dữ liệu thô cho tooltip
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
                    displayColors: false 
                }
            }
        }
    });
}

/**
 * 5. INPUT TAB LOGIC (EDIT MODE)
 */
/** Khởi tạo tab Input */

let INPUT_PAGE = 1; 
const INPUT_PAGE_SIZE = 50;
function initInputTab() {
    if(!MANUAL_CONFIG) {
        fetch('/get_manual_config').then(r=>r.json()).then(d => {
            MANUAL_CONFIG = d;
            INPUT_PAGE = 1; // Reset về trang 1 khi mới mở tab
            renderInputList();
        });
    } else {
        renderInputList();
    }
}
// Hàm render danh sách cuộn trong tab Input
function renderInputList() {
    const div = document.getElementById('inputListContainer');
    const search = document.getElementById('inputSearch').value.toUpperCase();
    
    // [THÊM MỚI] Lấy giá trị bộ lọc Cơ tính
    const filterProp = document.getElementById('inputFilterProp') ? document.getElementById('inputFilterProp').value : 'ALL';

    const allIds = Object.keys(RADAR_DATA).sort((a, b) => {
        const dateA = RADAR_DATA[a].production_date || '';
        const dateB = RADAR_DATA[b].production_date || '';
        
        const valA = parseDateRobust(dateA);
        const valB = parseDateRobust(dateB);
        
        if (valB !== valA) return valB - valA;
        return b.localeCompare(a, undefined, { numeric: true });
    });
    // Lọc dữ liệu: Kết hợp Tìm kiếm tên + Lọc Cơ tính
    let filteredIds = allIds.filter(id => {
        // 1. Lọc theo tên (Search)
        if (!id.includes(search)) return false;

        // 2. Lọc theo Cơ tính (Prop)
        if (filterProp !== 'ALL') {
            const data = RADAR_DATA[id] || {};
            // Kiểm tra xem cuộn này có bất kỳ chỉ số Cơ/Lý/Hóa nào > 0 hay không
            const hasProp = REAL_MECHANICAL_KEYS.some(k => (data[k] || 0) > 0);

            if (filterProp === 'NO' && hasProp) return false;  // Muốn tìm "Chưa có" mà cuộn này "Đã có" -> Loại
            if (filterProp === 'YES' && !hasProp) return false; // Muốn tìm "Đã có" mà cuộn này "Chưa có" -> Loại
        }

        return true;
    });
    const totalPages = Math.ceil(filteredIds.length / INPUT_PAGE_SIZE) || 1;
    if (INPUT_PAGE > totalPages) INPUT_PAGE = totalPages;
    if (INPUT_PAGE < 1) INPUT_PAGE = 1;

    const start = (INPUT_PAGE - 1) * INPUT_PAGE_SIZE;
    const displayIds = filteredIds.slice(start, start + INPUT_PAGE_SIZE);
    
    div.innerHTML = displayIds.map(id => {
        const isChecked = RADAR_DATA[id]['IS_CHECKED'] ? '✅' : '';
        const activeClass = (CURRENT_INPUT_COIL === id) ? 'active' : '';
        
        // 1. Logic Icon Cơ tính (Giữ nguyên)
        const hasPropRaw = REAL_MECHANICAL_KEYS.some(k => (RADAR_DATA[id][k] || 0) > 0);
        const propIcon = hasPropRaw ? '<span style="color:#16a34a; font-weight:bold; font-size:0.8em; margin-left:5px;">(Cơ tính)</span>' : '';

        // 2. [THÊM MỚI] Logic Icon Ngoại quan (Đếm số mục đã chấm)
        let countApp = 0;
        const totalApp = KEYS.APP_MANUAL.length;
        KEYS.APP_MANUAL.forEach(k => {
            if ((RADAR_DATA[id][k] || 0) > 0) countApp++;
        });

        let appIcon = '';
        if (countApp > 0) {
            // Style tối giản: Chữ xám, nền nhạt, ghi tắt là NQ
            appIcon = `<span style="font-size:0.8em; color:#475569; background:#f1f5f9; border:1px solid #e2e8f0; padding:0 4px; border-radius:3px; margin-left:5px; font-weight:600;">
                        NQ: ${countApp}/${totalApp}
                       </span>`;
        }

        // 3. Render HTML
        return `<div class="coil-item ${activeClass}" onclick="selectInputCoil('${id}')" id="in_${id}">
                    <div style="display:flex; align-items:center; flex-wrap:wrap;">
                        <span style="font-weight:600;">${id}</span> 
                        ${propIcon} 
                        ${appIcon}
                    </div>
                    <span>${isChecked}</span>
                </div>`;
    }).join('');
    
    document.getElementById('inputPageInfo').innerText = `${INPUT_PAGE} / ${totalPages}`;
}
// Hàm chuyển trang trong tab Input
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
// Hàm chọn cuộn để nhập liệu
function selectInputCoil(id) {
    CURRENT_INPUT_COIL = id;
    
    // 1. Lấy dữ liệu ngay lập tức từ biến toàn cục (RAM) -> KHÔNG CÓ ĐỘ TRỄ
    const coilData = RADAR_DATA[id] || {};
    document.getElementById('txtInputQuality').value = coilData['quality_level'] || '';
    
    // 2. Nhiệt độ & Tốc độ
    const temp = coilData['Temperature'] ? parseFloat(coilData['Temperature']).toFixed(0) : '--';
    const speed = coilData['Speed'] ? parseFloat(coilData['Speed']).toFixed(2) : '--';
    
    // 2. Thiết lập dữ liệu Gốc (Tham chiếu - Nét đứt)
    // Backend đã gửi sẵn trong auto_scores ở Bước 1
    ORIGINAL_SNAPSHOT = coilData['auto_scores'] ? JSON.parse(JSON.stringify(coilData['auto_scores'])) : {};
    
    // 3. Thiết lập dữ liệu Hiện tại (Đang sửa - Nét liền)
    INPUT_TEMP_DATA = {};
    const allDefectKeys = [
        ...UNIFIED_KEYS.SURFACE, ...UNIFIED_KEYS.GEO, 
        ...UNIFIED_KEYS.PROP, ...UNIFIED_KEYS.APP
    ];

    allDefectKeys.forEach(key => {
        // Ưu tiên lấy điểm đã lưu trong DB (nằm ngay level ngoài của coilData)
        if (coilData.hasOwnProperty(key)) {
            INPUT_TEMP_DATA[key] = coilData[key];
        } else {
            // Nếu chưa có điểm lưu, lấy điểm gốc làm mặc định
            INPUT_TEMP_DATA[key] = ORIGINAL_SNAPSHOT[key] || 0;
        }
    });

    // 4. Update UI ngay lập tức
    document.querySelectorAll('.coil-item').forEach(e => e.classList.remove('active'));
    document.getElementById(`in_${id}`)?.classList.add('active');
    document.getElementById('lblInputTemp').innerText = temp;
    document.getElementById('lblInputSpeed').innerText = speed;
    document.getElementById('inputEmpty').style.display = 'none';
    document.getElementById('radarInputArea').style.display = 'grid'; 
    document.getElementById('radarInputArea').style.opacity = '1'; // Bỏ hiệu ứng mờ loading
    document.getElementById('lblInputCoil').innerText = id;
    
    // 5. Vẽ biểu đồ
    drawInteractiveRadars();
}
// Hàm reset dữ liệu nhập về gốc (Máy đo)
function resetCurrentInput() {
    if(!CURRENT_INPUT_COIL) return;
    
    if(confirm('Khôi phục về dữ liệu gốc (Máy đo) và LƯU lại?')) {
        // 1. Revert dữ liệu tạm về Gốc (Auto Scores)
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
                const val = INPUT_TEMP_DATA[key] || 0;
                RADAR_DATA[CURRENT_INPUT_COIL][key] = val;
            });
            
            RADAR_DATA[CURRENT_INPUT_COIL]['IS_CHECKED'] = false;
        }

        // 4. Gửi dữ liệu xuống Backend (Cập nhật Database)
        const cleanScores = {};
        allDefectKeys.forEach(k => {
            if (INPUT_TEMP_DATA[k] !== undefined) {
                cleanScores[k] = INPUT_TEMP_DATA[k];
            } else {
                cleanScores[k] = 0;
            }
        });

        showLoading();
        fetch('/save_manual_data', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                coil_id: CURRENT_INPUT_COIL, 
                scores: cleanScores,
                is_reset: true
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
// Hàm lưu dữ liệu nhập tay
function saveManualData() {
    if(!CURRENT_INPUT_COIL) return;
    const qualityVal = document.getElementById('txtInputQuality').value.trim();
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
        body: JSON.stringify({ coil_id: CURRENT_INPUT_COIL, scores: cleanScores, user: 'QC_User',quality_level: qualityVal }) 
    }).then(r=>r.json()).then(d => {
        hideLoading();
        alert(d.msg);

        if(RADAR_DATA[CURRENT_INPUT_COIL]) {
            for (const [key, value] of Object.entries(cleanScores)) {
                RADAR_DATA[CURRENT_INPUT_COIL][key] = value;
            }
            RADAR_DATA[CURRENT_INPUT_COIL]['IS_CHECKED'] = true;
            RADAR_DATA[CURRENT_INPUT_COIL]['quality_level'] = qualityVal;
        }
        
        renderInputList();
        drawInteractiveRadars();
        calculateSummary(); 
    });
}
// Hàm vẽ các Radar tương tác trong tab Input
function drawInteractiveRadars() {
    const getData = (keys) => keys.map(k => INPUT_TEMP_DATA[k] || 0);

    // 1. BỀ MẶT (SURFACE)
    inputCharts.surf = createClickableRadar(
        'chartInSurf', 
        inputCharts.surf, 
        UNIFIED_KEYS.SURFACE, 
        getData(UNIFIED_KEYS.SURFACE), 
        'rgba(239,68,68,1)', 
        UNIFIED_KEYS.SURFACE 
    );
    // 2. HÌNH HỌC (GEOMETRY)
    inputCharts.geo = createClickableRadar(
        'chartInGeo', 
        inputCharts.geo, 
        UNIFIED_KEYS.GEO, 
        getData(UNIFIED_KEYS.GEO), 
        'rgba(59,130,246,1)', 
        UNIFIED_KEYS.GEO 
    );
    // 3. CƠ/LÝ/HÓA (PROP)
    inputCharts.prop = createClickableRadar(
        'chartInProp', 
        inputCharts.prop, 
        UNIFIED_KEYS.PROP, 
        getData(UNIFIED_KEYS.PROP), 
        'rgba(16,185,129,1)', 
        UNIFIED_KEYS.PROP 
    );
    // 4. NGOẠI QUAN (APP)
    inputCharts.app = createClickableRadar(
        'chartInApp', 
        inputCharts.app, 
        UNIFIED_KEYS.APP, 
        getData(UNIFIED_KEYS.APP), 
        'rgba(147,51,234,1)', 
        UNIFIED_KEYS.APP 
    );

}
// Biến toàn cục lưu trạng thái điểm đang sửa
let CURRENT_EDIT_KEY = null; 
let CURRENT_EDIT_CHART = null;

// Hàm tạo Radar có thể click để sửa điểm
function createClickableRadar(canvasId, oldChart, keys, currentData, color, editableKeys) {
    if (oldChart) oldChart.destroy();
    const cvs = document.getElementById(canvasId);
    const ctx = cvs.getContext('2d');
    const labels = keys.map(k => DEFECT_NAMES[k] || k);
    const originalData = keys.map(k => ORIGINAL_SNAPSHOT[k] || 0);

    return new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Đang sửa', // Label này sẽ hiện trong Tooltip
                    data: currentData,
                    borderColor: color,
                    backgroundColor: color.replace('1)', '0.15)'),
                    borderWidth: 3,
                    borderDash: [8, 6],
                    pointBackgroundColor: 'white',
                    pointBorderColor: (ctx) => {
                         const index = ctx.dataIndex;
                         const key = keys[index];
                         const val = INPUT_TEMP_DATA[key] || 0;
                         const oldVal = ORIGINAL_SNAPSHOT[key] || 0;
                         return (val != oldVal) ? '#dc2626' : color; 
                    },
                    pointRadius: 5,
                    pointHoverRadius: 8, // Hover vào point sẽ to lên
                    order: 1
                },
                {
                    label: 'Gốc',
                    data: originalData,
                    borderColor: '#64748b',
                    backgroundColor: 'rgba(148, 163, 184, 0.2)',
                    borderWidth: 2,
                    pointRadius: 0,
                    pointHoverRadius: 0,
                    order: 2
                }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false, animation: false,
            scales: {
                r: {
                    min: 0, max: 6,
                    ticks: { display: false, stepSize: 1 },
                    pointLabels: {
                        font: { size: 12, weight: 'bold' },
                        color: (c) => { // Tô đỏ tên lỗi nếu có thay đổi
                            const key = keys[c.index];
                            return (INPUT_TEMP_DATA[key] != ORIGINAL_SNAPSHOT[key]) ? '#dc2626' : '#334155';
                        }
                    }
                }
            },
            plugins: {
                legend: { display: false }, // Ẩn legend cho gọn
                // --- 1. HIỆN TOOLTIP KHI HOVER POINT ---
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    callbacks: {
                        label: function(context) {
                            // Hiện: "Tên lỗi: C3"
                            return ` ${context.dataset.label}: C${context.raw}`;
                        }
                    }
                }
            },
            // --- 2. LOGIC CLICK VÀO TÊN LỖI ---
            onClick: (e, activeElements, chart) => {
                const pos = Chart.helpers.getRelativePosition(e, chart);
                // Tính khoảng cách từ tâm đến điểm click
                const rScale = chart.scales.r;
                const dx = pos.x - rScale.xCenter;
                const dy = pos.y - rScale.yCenter;
                const dist = Math.sqrt(dx*dx + dy*dy);

                const chartRadius = rScale.drawingArea;
                if (dist > chartRadius * 0.9) {
                    const idx = getIndexFromAngle(pos, chart, keys.length);
                    if (idx !== -1 && editableKeys.includes(keys[idx])) {
                        const key = keys[idx];
                        openScorePopup(e.native, key, INPUT_TEMP_DATA[key]||0, DEFECT_NAMES[key]||key, chart);
                    }
                }
            }
        }
    });
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
    
    popup.style.display = 'block'; // Hiển thị trước để tính kích thước

    const pW = popup.offsetWidth;
    const pH = popup.offsetHeight;
    const winW = window.innerWidth;
    const winH = window.innerHeight;

    let left = event.clientX + 10;
    let top = event.clientY + 10;


    if (left + pW > winW) {
        left = event.clientX - pW - 10;
    }

    if (top + pH > winH) {
        top = winH - pH - 10;
    }
    popup.style.position = 'fixed'; 
    popup.style.left = left + 'px';
    popup.style.top = top + 'px';
    
    // Focus ô input
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
// Hàm xác nhận điểm từ popup
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
// Đóng popup khi click ra ngoài
document.addEventListener('click', function(event) {
    const popup = document.getElementById('scoreInputPopup');
    const isClickInside = popup.contains(event.target);
    if (!isClickInside && event.target.tagName !== 'CANVAS' && popup.style.display === 'block') {
    }
});
// Radar Hover State
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
/**
 * 6. NAVIGATION & MODAL LOGIC
 */
// Hàm chuyển nhóm tab chính
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
// Hàm render danh sách trong tab cụ thể
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
// Hàm vẽ bảng với phân trang
function drawTable(name) {
    const conf = TAB_PAGING[name];
    const start = (conf.page - 1) * PAGE_SIZE;
    const items = conf.data.slice(start, start + PAGE_SIZE);
    
    document.getElementById(`tbody_${name}`).innerHTML = items.map((r, i) => {

        const coilId = r['Cuộn'];
        const grade = (RADAR_DATA[coilId] && RADAR_DATA[coilId].GRADE) ? RADAR_DATA[coilId].GRADE : '---';
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
// Hàm chuyển trang trong bảng
function changeTabPage(name, d) {
    const conf = TAB_PAGING[name];
    if(conf.page+d >= 1 && conf.page+d <= Math.ceil(conf.data.length/PAGE_SIZE)) { conf.page += d; drawTable(name); }
}
// Hàm kích hoạt quét Batch
function triggerBatchSync() {
    const rawIds = document.getElementById('txtBatchCoils').value.trim();
    const currentGrade = document.getElementById('globalGradeSelect').value;
    const currentFactory = document.getElementById('globalFactorySelect').value;

    if (!rawIds) return alert("⚠️ Thiếu ID!");

    showLoading();
    fetch('/api/sync_batch_coils', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            coil_ids: rawIds,
            grade: currentGrade,
            factory: currentFactory // <--- GỬI KÈM
        })
    })
    .then(response => response.json())
    .then(data => {
        hideLoading();
        if (data.status === 'success') {
            alert(`✅ ${data.msg}`);
            document.getElementById('txtBatchCoils').value = ''; 
        } else {
            alert(`❌ Lỗi: ${data.msg}`);
        }
    })
    .catch(err => {
        hideLoading();
        alert("❌ Lỗi kết nối Server: " + err);
    });
}
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
    const d = RADAR_DATA[id] || {};
    const qual = d['quality_level'] || '---';
    const temp = d['Temperature'] ? parseFloat(d['Temperature']).toFixed(0) : '--';
    const speed = d['Speed'] ? parseFloat(d['Speed']).toFixed(2) : '--';
    document.getElementById('modalStats').style.display = 'flex'; 
    document.getElementById('valModalQual').innerText = qual;
    document.getElementById('valModalTemp').innerText = temp;
    document.getElementById('valModalSpeed').innerText = speed;

    setTimeout(() => drawCoilRadar(id), 50);
}
function drawCoilRadar(id){
    const s = RADAR_DATA[id] || {};
    // Hàm get data cũ
    const getData = (keys) => ({ 
        labels: keys.map(k=>DEFECT_NAMES[k]||k), 
        data: keys.map(k=>s[k]||0),
        keys: keys 
    });
    
    const dSurf = getData(UNIFIED_KEYS.SURFACE);
    const dGeo  = getData(UNIFIED_KEYS.GEO);
    const dProp = getData(UNIFIED_KEYS.PROP);
    const dApp  = getData(UNIFIED_KEYS.APP);
    mc1 = renderMiniRadar('chartModalSurf', mc1, dSurf.labels, dSurf.data, 'rgba(239,68,68,1)',   id, dSurf.keys);
    mc2 = renderMiniRadar('chartModalGeo',  mc2, dGeo.labels,  dGeo.data,  'rgba(59,130,246,1)',   id, dGeo.keys);
    mc3 = renderMiniRadar('chartModalProp', mc3, dProp.labels, dProp.data, 'rgba(16,185,129,1)',   id, dProp.keys);
    mc4 = renderMiniRadar('chartModalApp',  mc4, dApp.labels,  dApp.data,  'rgba(147,51,234,1)',   id, dApp.keys);
}

function showLoading(){document.getElementById('loadingOverlay').style.display='flex'}
function hideLoading(){document.getElementById('loadingOverlay').style.display='none'}
function resetFilters() { 
    document.getElementById('f_surf').value='ALL'; 
    document.getElementById('f_geo').value='ALL'; 
    
    // [SỬA]: Reset 2 ô lọc mới
    if(document.getElementById('f_mech')) document.getElementById('f_mech').value='ALL'; 
    if(document.getElementById('f_chem')) document.getElementById('f_chem').value='ALL'; 
    
    if(document.getElementById('f_app')) document.getElementById('f_app').value='ALL'; 
    document.getElementById('s_full').value=''; 
    applyFilters(); 
}
function filterSummaryTable(type) {
    resetFilters();
    
    // [SỬA]: Hàm helper setF nhận 4 tham số: Surf, Geo, Mech, Chem
    const setF = (s, g, m, c) => { 
        document.getElementById('f_surf').value = s; 
        document.getElementById('f_geo').value = g; 
        if(document.getElementById('f_mech')) document.getElementById('f_mech').value = m; 
        if(document.getElementById('f_chem')) document.getElementById('f_chem').value = c; 
    };

    if (type === 'FULL') {
        setF('YES', 'YES', 'YES', 'YES');
    } 
    else if (type === 'GEO_PROP') {
        setF('NO', 'YES', 'ALL', 'YES'); 
    }
    else if (type === 'SURF_GEO') {
        setF('YES', 'YES', 'ALL', 'ALL');
    }
    else if (type === 'SURF_PROP') {
        setF('YES', 'NO', 'ALL', 'YES');
    }
    
    applyFilters();
}

function getRawDetailString(coilId, key) {
    if (!coilId || !RADAR_DATA[coilId] || !RADAR_DATA[coilId].raw_data) {
        return null; 
    }
    const val = RADAR_DATA[coilId].raw_data[key];

    if (typeof val === 'string') {
        return val; 
    }
    if (typeof val === 'number') {
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

        const currentVal = select.getAttribute('data-current') || 'ALL'; 
        
        select.innerHTML = '';
        const optAll = document.createElement('option');
        optAll.value = 'ALL';
        optAll.innerText = '-- Tất cả --';
        if(currentVal === 'ALL') optAll.selected = true;
        select.appendChild(optAll);

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

function changeGlobalContext() {
    const factory = document.getElementById('globalFactorySelect').value;
    const grade = document.getElementById('globalGradeSelect').value;
    const dStart = document.getElementById('globalDateStart').value;
    const dEnd = document.getElementById('globalDateEnd').value;
    window.location.href = `?factory=${factory}&grade=${grade}&start_date=${dStart}&end_date=${dEnd}`;
}
function resetGlobalDate() {
    document.getElementById('globalDateStart').value = '';
    document.getElementById('globalDateEnd').value = '';
    changeGlobalContext();
}
// --- JAVASCRIPT XỬ LÝ QUÉT LIVE ---
function triggerLiveSync() {
    const coilId = document.getElementById('txtLiveCoilId').value.trim();
    const currentGrade = document.getElementById('globalGradeSelect').value;
    const currentFactory = document.getElementById('globalFactorySelect').value;
    if (!coilId) return alert("⚠️ Thiếu ID!");
    showLoading();
    fetch('/api/sync_single_coil', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
            coil_id: coilId,
            grade: currentGrade,
            factory: currentFactory  
        })
    })
    .then(r => r.json())
    .then(data => {
        hideLoading();
        alert(data.msg);
        if(data.status === 'success') location.reload();
    })
    .catch(e => { hideLoading(); alert(e); });
}

window.addEventListener('load', () => {
    const urlParams = new URLSearchParams(window.location.search);
    
    // 1. Set Factory Dropdown
    const factoryParam = urlParams.get('factory') || 'HRC1';
    const factorySelect = document.getElementById('globalFactorySelect');
    if(factorySelect) factorySelect.value = factoryParam;

    // 2. Set Grade Dropdown
    const gradeParam = urlParams.get('grade'); 
    
    if(gradeParam) {
        const select = document.getElementById('globalGradeSelect');
        if(select) {
            select.setAttribute('data-current', gradeParam); 
            select.value = gradeParam;
        }
    }

    loadGradeList();
});
function changeFullPage(d) { const max = Math.ceil(CURRENT_VIEW_LIST.length/50); if(FULL_PAGE+d>=1 && FULL_PAGE+d<=max) { FULL_PAGE+=d; renderFullTable(); } }
function upAjax(u,i){ const f=document.getElementById(i).files[0]; if(!f)return alert('Chọn file!'); const fd=new FormData(); fd.append('file',f); showLoading(); fetch(u,{method:'POST',body:fd}).then(r=>r.json()).then(d=>{alert(d.msg);location.reload()}).catch(e=>{hideLoading();alert('Lỗi:'+e)}); }
function deleteData(cat){ if(confirm('Xóa dữ liệu?')) { showLoading(); fetch('/delete_data_category',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category:cat})}).then(r=>r.json()).then(d=>{alert(d.msg);location.reload()}).catch(e=>alert(e)); }}
function delCfg(e,n){e.stopPropagation();if(confirm('Xóa?'))fetch('/delete_config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})}).then(()=>location.reload())}