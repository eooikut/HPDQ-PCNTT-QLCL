let PREVIEW_ORDER_LIST = []; // Biến lưu danh sách Order cho Dropdown

// Hàm tải danh sách Order
async function loadPreviewOrderList() {
    try {
        const res = await fetch('/api/get_preview_order_list');
        const d = await res.json();
        if (d.status === 'success') {
            PREVIEW_ORDER_LIST = d.data;
        }
    } catch(err) {
        console.error("Lỗi tải danh sách Order Preview:", err);
    }
}
/**
 * 1. CONSTANTS & CONFIGURATION
 * Định nghĩa các hằng số dùng chung toàn hệ thống
 */
const KEYS = {
    SURFACE_AUTO: ['MI', 'HPrScale', 'EL', 'HOLE', 'RIP', 'BRUS', 'LC', 'SCRT','XC', 'XTC','TCPK-n'],
    SURFACE_MANUAL: ['oil', 'rust', 'scratch_m', 'dirt',  'other_s', 'gianbien','chambi'],
    GEO_AUTO: ['Crown', 'Wedge', 'ThickDiff', 'WidthDiff'],
    GEO_MANUAL: ['telescope' , 'high_spot', 'dungsaitrong'],

    MECH_AUTO: ['YieldPoint', 'Tensile', 'Elongation', 'Hardness','ImpactEnergy'],
    CHEM_AUTO: ['C', 'Mn', 'Si', 'P', 'S', 'Cu', 'Ni', 'Cr', 'Mo', 'V', 'Ti', 'Al', 'Ca', 'B', 'Nb', 'CEV', 'O', 'N', 'H'],
    
    APP_MANUAL: ['strap', 'label_tag', 'packaging', 'edge_cond', 'coil_shape', 'mop_bien']
};

// Thứ tự hiển thị thống nhất trên mọi biểu đồ
const UNIFIED_KEYS = {
    SURFACE: [...KEYS.SURFACE_MANUAL, ...KEYS.SURFACE_AUTO],
    GEO:     [...KEYS.GEO_MANUAL,     ...KEYS.GEO_AUTO],
    PROP:    [...KEYS.MECH_AUTO,      ...KEYS.CHEM_AUTO],
    APP:     [...KEYS.APP_MANUAL]
};
let SESSION_SNAPSHOT = {};
const REAL_MECHANICAL_KEYS = ['YieldPoint', 'Tensile', 'Elongation', 'Hardness'];
const DEFECT_NAMES = {
    'MI': 'TCPK nặng', 
    'HPrScale': 'Xỉ sơ cấp HP', 
    'EL': ' Lỗi xếp lớp',
    'HOLE': 'Lỗ thủng', 
    'RIP': 'Rách bề mặt', 
    'BRUS': 'Vết Hằn trục',
    'LC': 'Nứt dọc', 
    'SCRT': 'Xước bề mặt',
	'TCPK-n': 'TCPK nhẹ',
    'oil': 'Gấp nếp', 
    'rust': 'Nếp nhăn', 
    'scratch_m': 'Vết hằn Pinch Roll',
    'dirt': 'Gãy mặt', 
    'XTC': 'Xỉ thứ cấp', 
    'XC': 'Xỉ cán', 
    'other_s': 'Xỉ muối tiêu',
    'gianbien': 'Giãn biên/Bụng',
    'chambi': 'Chấm bi',
	'high_spot': 'High Spot',
    'dungsaitrong': 'Dung sai ĐK trong',
    'Crown': 'Độ Crown', 
    'Wedge': 'Độ Wedge',
    'ThickDiff': 'Sai lệch dày', 
    'WidthDiff': 'Sai lệch rộng',
    'telescope': 'Cong cạnh',
    'YieldPoint': 'GH Chảy', 
    'Tensile': 'GH Bền', 
    'Elongation': 'Độ giãn dài',
    'Hardness': 'Độ cứng',
    'ImpactEnergy': 'Độ dai va đập',
    'C': 'Carbon', 
    'Mn': 'Mangan', 
    'Si': 'Silic', 
    'P': 'Photpho', 
    'S': 'Lưu huỳnh',
    'Cu': 'Đồng', 
    'Ni': 'Niken', 
    'Cr': 'Crom', 
    'Mo': 'Moly', 
    'V': 'Vanadi', 
    'Ti': 'Titan', 
    'Al': 'Nhôm', 
    'Ca': 'Canxi', 
    'B': 'Bo', 
    'Nb': 'Niobi', 
    'CEV': 'CEV', 
    'O': 'Oxy', 
    'N': 'Nitơ', 
    'H': 'Hydro',
    'strap': 'Khuyết biên', 
    'label_tag': 'Bavia biên', 
    'packaging': 'Vỡ biên',
    'edge_cond': 'Sổ vòng', 
    'coil_shape': 'Loa cuộn',
    'mop_bien': 'Móp biên'
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
function calculateSummary(isAutoSync = false) {
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

    applyFilters(isAutoSync);
}

function applyFilters(isAutoSync = false) {
    if (!isAutoSync) {
        FULL_PAGE = 1;
    }
    const valQClass = document.getElementById('f_qclass') ? document.getElementById('f_qclass').value : 'ALL';
    const valPStatus = document.getElementById('f_pstatus') ? document.getElementById('f_pstatus').value : 'ALL';
    const valRework = document.getElementById('f_rework') ? document.getElementById('f_rework').value : 'ALL'; 
    const valQCStatus = document.getElementById('f_qcstatus') ? document.getElementById('f_qcstatus').value : 'ALL'; 
    
    const searchRaw = document.getElementById('s_full').value.toUpperCase().trim();
    const searchTerms = searchRaw.split(/[\s,\n]+/).filter(t => t.length > 0);
    
    const orderRaw = document.getElementById('s_order_sum') ? document.getElementById('s_order_sum').value.toUpperCase().trim() : '';
    const orderTerms = orderRaw.split(/[\s,\n]+/).filter(t => t.length > 0);
    
    CURRENT_VIEW_LIST = ALL_IDS_LIST.filter(id => {
        const s = RADAR_DATA[id] || {};
        const idUpper = id.toUpperCase();
        const idXulyUpper = (s['ID_xuly'] || '').toUpperCase();
        
        const orderUpper = String(s['original_order'] || '').toUpperCase();
        
        const matchesSearch = searchTerms.length === 0 || searchTerms.some(term => idUpper.includes(term) || idXulyUpper.includes(term));
        if (!matchesSearch) return false;
        
        const matchesOrder = orderTerms.length === 0 || orderTerms.some(term => orderUpper.includes(term));
        if (!matchesOrder) return false;

        const sQClass = s['quality_class'] || 'NULL';
        const sPStatus = s['prime_status'] || 'NULL';
        const sRework = s['rework_status'] || 'NULL';
        const sStatus = s['qc_status'] || 'PENDING'; 

        if (valQClass !== 'ALL' && sQClass !== valQClass) return false;
        if (valPStatus !== 'ALL' && sPStatus !== valPStatus) return false;
        if (valRework !== 'ALL' && sRework !== valRework) return false; 
        
        if (valQCStatus !== 'ALL') {
            if (sStatus !== valQCStatus) return false;
        }

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
    const tableWrapper = tbody.closest('.table-wrapper');
    const currentScroll = tableWrapper ? tableWrapper.scrollTop : 0;
    tbody.innerHTML = items.map((id, i) => {
        const s = RADAR_DATA[id] || {};
        const grade = s['GRADE'] || '---';
        let prodDate = s['production_date'] || '';
        let timeOnly = '---';
        if (prodDate && prodDate.includes(' ')) {
            // VD: "2025-04-08 16:06:58.000" -> Tách qua khoảng trắng lấy "16:06:58.000"
            let timeParts = prodDate.split(' ')[1]; 
            if (timeParts) {
                timeOnly = timeParts.substring(0, 5); // Lấy "16:06"
            }
        }
        let thick = parseFloat(s['target_thick']) || 0;
        // Nếu thick = 0 thì lấy giá trị dự phòng từ TARGET_LV2
        if (thick === 0) {
            thick = parseFloat(s['TARGET_LV2']) || 0;
        }
        let width = parseFloat(s['target_width']) || 0;
        
        let txw = '---';
        if (thick > 0 || width > 0) {
            let thickDisplay = thick.toFixed(2); // Dày luôn lấy 2 số thập phân
            let widthDisplay = Number.isInteger(width) ? width : width.toFixed(1); // Rộng nếu nguyên thì không lấy phẩy
            txw = `${thickDisplay}x${widthDisplay}`;
        }
        // Xử lý Ghi chú
        const orderNum = s['original_order'] || '---';
        const qcMsgText = s['qc_msg'] || '---';
        let noteStr = s['note_qc'] || '';
        let note = noteStr; 
        try {
            let obj = JSON.parse(noteStr);
            let arr = [];
            if (obj.surf) arr.push(obj.surf);
            if (obj.geo) arr.push(obj.geo);
            if (obj.prop) arr.push(obj.prop);
            if (obj.app) arr.push(obj.app);
            note = arr.join(', ');
        } catch(e) {}
        
        const idXuly = s['ID_xuly'] || '';
        const nhom = s['Nhom'] || '-';
        const displayId = idXuly 
            ? `${idXuly}<br><small style="color:#64748b; font-weight:normal; font-size: 0.8em;">Gốc: ${id}</small>` 
            : id;
        
        // CÁC BIẾN TRẠNG THÁI MỚI
        let weightVal = parseFloat(s['weight']) || 0;
        const weight = weightVal.toLocaleString('vi-VN');
        
        const qClass = s['quality_class'] || '---';
        const pStatus = s['prime_status'] || '---';
        const rStatus = s['rework_status'] || '---';
        const rawMappedPo = s['mapped_po'];
        let mappedPoBadge = '';

        const canRemovePO = USER_ROLE === 'admin' || USER_PERMISSIONS.includes('qlcl_remove_po');
        const btnRemoveHTML = canRemovePO 
            ? `<button onclick="removeMappedPo('${id}')" title="Gỡ cờ, đưa về Tồn kho" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:1.1em; padding:0; line-height:1;">✖</button>` 
            : '';

        // 1. Trường hợp NULL hoặc Rỗng (Hàng Tồn Kho Nguyên Bản)
        if (rawMappedPo === null || rawMappedPo === undefined || String(rawMappedPo).trim() === '') {
            mappedPoBadge = `<span style="color:#94a3b8; font-size:0.85em; font-weight: 500;">---</span>`;
        } 
        else {
            const mappedPoStr = String(rawMappedPo).trim();
            
            // 2. Trường hợp '0' (Hàng đã bị gỡ cờ / Trả kho)
            if (mappedPoStr === '0') {
                mappedPoBadge = `<span style="color:#64748b; font-size:0.85em; font-weight:600; border: 1px dashed #cbd5e1; padding: 2px 6px; border-radius: 4px; background: #f8fafc;" title="Tồn không cờ">Tồn không cờ</span>`;
            } 
            // 3. Trường hợp '1' (Hàng đang chờ gán SO)
            else if (mappedPoStr === '1') {
                mappedPoBadge = `
                    <div style="display:flex; align-items:center; justify-content:center; gap:5px;">
                        <span style="background:#fef08a; color:#854d0e; padding:2px 6px; border-radius:4px; font-weight:bold; font-size:0.85em;">Chờ SO</span>
                        <button onclick="removeMappedPo('${id}')" title="Gỡ cờ, đưa về Tồn kho" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:1.1em; padding:0; line-height:1;">
                            ✖
                        </button>
                    </div>
                `;
            } 
            // 4. Trường hợp có Mã SO cụ thể (SO-123...)
            else {
                mappedPoBadge = `
                    <div style="display:flex; align-items:center; justify-content:center; gap:5px;">
                        <span style="background:#dbeafe; color:#1e40af; padding:2px 6px; border-radius:4px; font-weight:bold; font-size:0.85em;">${mappedPoStr}</span>
                        <button onclick="removeMappedPo('${id}')" title="Gỡ cờ, đưa về Tồn kho" style="background:none; border:none; color:#ef4444; cursor:pointer; font-size:1.1em; padding:0; line-height:1;">
                            ✖
                        </button>
                    </div>
                `;
            }
        }
        const classBadge = qClass === 'LOAI_1' ? `<span style="color:#15803d; font-weight:bold;">${qClass}</span>` : (qClass === 'LOAI_2' ? `<span style="color:#475569; font-weight:bold;">${qClass}</span>` : '---');
        const primeBadge = pStatus === 'PRIME' ? `<span style="background:#dcfce7; color:#15803d; padding:2px 6px; border-radius:4px; font-weight:bold;">PRIME</span>` : (pStatus === 'NON_PRIME' ? `<span style="background:#fef3c7; color:#b45309; padding:2px 6px; border-radius:4px; font-weight:bold;">NON-PRIME</span>` : (pStatus === 'SCRAP' ? `<span style="background:#f1f5f9; color:#475569; padding:2px 6px; border-radius:4px; font-weight:bold;">SCRAP</span>` : '---'));
        const reworkBadge = rStatus === 'FINAL' ? `<span style="color:#0369a1; font-weight:bold;">FINAL</span>` : (rStatus === 'NULL' ? '---' : `<span style="color:#ea580c; font-weight:bold;">${rStatus}</span>`);

        const status = s['qc_status'] || 'PENDING';
        let statusBadge = '';
        if (status === 'PASS') {
            statusBadge = `<span style="background:#dcfce7; color:#15803d; padding:3px 8px; border-radius:4px; font-weight:bold;">PASS</span>`;
        } else if (status === 'FAIL') {
            statusBadge = `<span style="background:#fee2e2; color:#b91c1c; padding:3px 8px; border-radius:4px; font-weight:bold;">FAIL</span>`;
        } else if (status === 'FAILNOCHEM') {
            statusBadge = `<span style="background:#ffedd5; color:#ea580c; padding:3px 8px; border-radius:4px; font-weight:bold; font-size:0.9em;">FAILNOCHEM</span>`;
        } else if (status === 'PASSNOCHEM') {
            statusBadge = `<span style="background:#e0f2fe; color:#0369a1; padding:3px 8px; border-radius:4px; font-weight:bold; font-size:0.9em;">PASSNOCHEM</span>`;
        } else {
            statusBadge = `<span style="background:#f1f5f9; color:#475569; padding:3px 8px; border-radius:4px; font-weight:bold;">${status}</span>`;
        }

        // 🌟 LẤY MÃ TDC CODE
        let tdcCode = s['tdc_code'] || '---';
        if (tdcCode !== '---' && tdcCode !== '') {
            const tdcUrl = `/tdc_manager?focus_tdc=${encodeURIComponent(tdcCode)}`;
            tdcCode = `<a href="${tdcUrl}" target="tdc_manager_window" 
                          style="font-size:0.85em; color:#0284c7; font-weight:bold; text-decoration:underline; cursor:pointer; transition: color 0.2s;"
                          onmouseover="this.style.color='#0369a1'" 
                          onmouseout="this.style.color='#0284c7'"
                          title="Click để mở chi tiết Tiêu chuẩn này">
                          ${tdcCode}
                       </a>`;
        } else {
            tdcCode = `<span style="font-size:0.85em; color:#94a3b8;">---</span>`;
        }

        const radarBtn = `<button onclick="showModal('${id}', 'Chi tiết: ${idXuly || id}')" 
                                  style="background:#e0f2fe; color:#0284c7; border:1px solid #bae6fd; border-radius:4px; padding:4px 8px; cursor:pointer; font-weight:bold; font-size:0.85em; white-space:nowrap;">
                              Radar
                          </button>`;
        const s1 = parseFloat(s['stage1_penalty']) || 0;
        const s2 = parseFloat(s['stage2_penalty']) || 0;
        
        // Bôi vàng nếu Lỗi cơ tính (stage 2). 
        // Nếu bạn muốn bắt buộc CẢ 2 khâu đều bị phạt thì đổi thành: (s1 > 0 && s2 > 0)
  //      const isMechanicalFail = (s1 === 0 && s2 > 0);
		const isMechanicalFail = (s2 > 0);
        const trStyle = isMechanicalFail ? 'background-color: #fef9c3;' : '';    
        return `<tr style="${trStyle}">
            <td style="text-align: center;">${start + i + 1}</td>
            <td style="font-weight:bold;color:#333">${displayId}</td>
            <td style="text-align: center; color: #64748b; font-weight: 600; font-family: monospace; font-size: 1em;">${timeOnly}</td>
            <td style="text-align: center;"><span style="font-weight:600; color:#475569; background:#f1f5f9; padding:2px 8px; border-radius:4px;">${grade}</span></td>
            <td style="text-align: center; color: #334155; font-weight: 600; font-size: 0.9em;">${txw}</td>
            <td style="text-align:right; font-weight:bold; color:#0f172a;">${weight}</td>
            <td style="text-align: center; font-weight: bold; color: #475569;">${nhom}</td>
            <td style="text-align: center;">${classBadge}</td>
            <td style="text-align: center;">${primeBadge}</td>
            <td style="text-align: center;">${reworkBadge}</td>
            <td style="text-align: center;">${statusBadge}</td>
            <td style="text-align: center; font-weight: 600; color: #475569;">${orderNum}</td>
            <td style="text-align: center;">${mappedPoBadge}</td>
            <td style="text-align: center;">${tdcCode}</td>
            
            <td style="text-align: left; color: #dc2626; font-size: 0.9em; font-weight: 500; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${qcMsgText}">
                ${qcMsgText}
            </td>
            
            <td style="text-align: center;">${radarBtn}</td>
            <td style="padding: 0;">
                <div id="note_view_${id}" class="note-cell" style="padding: 8px 10px; min-height: 20px;">
                    ${note}
                </div>
            </td>
        </tr>`;
    }).join('');
    
    const maxPage = Math.ceil(CURRENT_VIEW_LIST.length / 50) || 1;
    document.getElementById('pinfo_full').innerText = `${FULL_PAGE} / ${maxPage}`;
    if (tableWrapper) tableWrapper.scrollTop = currentScroll;
}
function renderNoteCell(coilId, text) {
    renderFullTable(); 
}
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
    
    let datasets = [];

    // NẾU CÓ coilId và keys (Tức là đang xem Radar của 1 cuộn cụ thể trong Modal)
    if (coilId && keys && RADAR_DATA[coilId]) {
        const limits = RADAR_DATA[coilId].tdc_limits || {};
        
        // Lấy dải giới hạn, mặc định Max = 1, Min = 0 nếu TDC không có cấu hình
        const limitMaxData = keys.map(k => limits[k] !== undefined ? limits[k].max : 1);
        const limitMinData = keys.map(k => limits[k] !== undefined ? limits[k].min : 0);

        datasets = [
            // 1. VIỀN TDC MAX
            {
                label: 'Giới hạn TDC Max',
                data: limitMaxData,
                borderColor: '#16a34a',
                borderWidth: 2,
                borderDash: [5, 5],
                pointRadius: 0,
                fill: false,
                order: 4
            },
            // 2. VIỀN TDC MIN (Tô nền xanh nhạt bao quát dải TDC)
            {
                label: 'Giới hạn TDC Min',
                data: limitMinData,
                borderColor: '#16a34a',
                borderWidth: 2,
                borderDash: [5, 5],
                pointRadius: 0,
                fill: '-1', // Đổ màu lên dính vào TDC Max
                backgroundColor: 'rgba(22, 163, 74, 0.15)',
                order: 3
            },
            // 3. ĐIỂM THỰC TẾ CỦA CUỘN
            {
                label: 'Điểm', 
                data: data,
                borderColor: color, 
                backgroundColor: 'transparent', // Giữ trong suốt để nhìn xuyên qua thấy vùng xanh TDC
                borderWidth: 2, 
                pointBackgroundColor: '#fff', 
                pointRadius: 4,
                pointHoverRadius: 7,
                order: 1
            }
        ];
    } else {
        // NẾU KHÔNG CÓ coilId (Tức là Radar biểu đồ trung bình ở đầu tab SUMMARY)
        datasets = [
            {
                label: 'Điểm', 
                data: data,
                borderColor: color, 
                backgroundColor: color.replace('1)', '0.2)'), // Tô màu nền bình thường
                borderWidth: 2, 
                pointBackgroundColor: '#fff', 
                pointRadius: 3,
                pointHoverRadius: 6
            }
        ];
    }

    return new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: datasets
        },
        options: {
            responsive: true, 
            maintainAspectRatio: false,
            scales: { 
                r: { 
                    min: 0, max: 6, 
                    ticks: { display: false, stepSize: 1 }, 
                    pointLabels: { font: { size: 11, weight: 'bold' } } 
                } 
            },
            plugins: { 
                legend: { display: false },
                tooltip: {
                    enabled: true,
                    callbacks: {
                        label: function(context) {
                            // Ẩn các label viền TDC khỏi tooltip cho đỡ rối mắt
                            if (context.dataset.label.includes('TDC')) return null; 
                            return ` Điểm phân hạng: C${context.raw}`;
                        },
                        afterLabel: function(context) {
                            // Hiển thị tooltip dữ liệu gốc (Nếu có)
                            if (coilId && keys && context.dataset.label === 'Điểm') {
                                const index = context.dataIndex;
                                const originalKey = keys[index]; 
                                const detail = getRawDetailString(coilId, originalKey);
                                if (detail) {
                                    if (Array.isArray(detail)) return detail;
                                    return ` ${detail}`;
                                }
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
    const currentScroll = div ? div.scrollTop : 0;
    const searchRaw = document.getElementById('inputSearch').value.toUpperCase().trim();
    const searchTerms = searchRaw.split(/[\s,\n,]+/).map(t => t.trim()).filter(t => t.length > 0);
	
    const orderRaw = document.getElementById('inputSearchOrder') ? document.getElementById('inputSearchOrder').value.toUpperCase().trim() : '';
    const orderTerms = orderRaw.split(/[\s,\n,]+/).map(t => t.trim()).filter(t => t.length > 0);
    // [THÊM MỚI] Lấy giá trị bộ lọc Cơ tính
    const filterRework = document.getElementById('inputFilterRework') ? document.getElementById('inputFilterRework').value : 'ALL';
    const filterQCStatus = document.getElementById('inputFilterQCStatus') ? document.getElementById('inputFilterQCStatus').value : 'ALL';
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
        const idUpper = id.toUpperCase();
		const data = RADAR_DATA[id] || {};
		const idXulyUpper = (data['ID_xuly'] || '').toUpperCase(); 
        
        // 🌟 Lấy Order của cuộn hiện tại
        const orderUpper = String(data['original_order'] || '').toUpperCase();
        
        const matchesSearch = searchTerms.length === 0 || 
                            searchTerms.some(term => idUpper.includes(term) || idXulyUpper.includes(term));
        if (!matchesSearch) return false;
        
        // 🌟 Check khớp Order
		const matchesOrder = orderTerms.length === 0 || 
                            orderTerms.some(term => orderUpper.includes(term));
        if (!matchesOrder) return false;

        // 🌟 Lọc theo Rework Status
        if (filterRework !== 'ALL') {
            const currentRework = data['rework_status'] || 'NULL';
            if (currentRework !== filterRework) return false;
        }
        if (filterQCStatus !== 'ALL') {
            const currentQCStatus = data['qc_status'] || 'PENDING';
            if (currentQCStatus !== filterQCStatus) return false;
        }
        return true;
    });
    const totalPages = Math.ceil(filteredIds.length / INPUT_PAGE_SIZE) || 1;
    if (INPUT_PAGE > totalPages) INPUT_PAGE = totalPages;
    if (INPUT_PAGE < 1) INPUT_PAGE = 1;

    const start = (INPUT_PAGE - 1) * INPUT_PAGE_SIZE;
    const displayIds = filteredIds.slice(start, start + INPUT_PAGE_SIZE);
    
    div.innerHTML = displayIds.map(id => {
		const idUpper = id.toUpperCase();
		const data = RADAR_DATA[id] || {};
        const isChecked = RADAR_DATA[id]['IS_CHECKED'] ? '✅' : '';
        const activeClass = (CURRENT_INPUT_COIL === id) ? 'active' : '';
        const idXuly = data['ID_xuly'] || '';
        const displayId = idXuly ? `${idXuly} <br><small style="color:#94a3b8; font-weight:normal;">Gốc: ${id}</small>` : id;
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
        const s1 = parseFloat(data['stage1_penalty']) || 0;
        const s2 = parseFloat(data['stage2_penalty']) || 0;
//        const isMechanicalFail = (s1 === 0 && s2 > 0);
        const isMechanicalFail = ( s2 > 0);
        // Thêm nền vàng nhạt và vạch kẻ viền bên trái cho dễ nhận diện
        const highlightStyle = isMechanicalFail ? 'background-color: #fef9c3; border-left: 4px solid #f59e0b;' : '';
        // 3. Render HTML
        return `<div class="coil-item ${activeClass}" onclick="selectInputCoil('${id}')" id="in_${id}" style="${highlightStyle}">
                    <div style="display:flex; align-items:center; flex-wrap:wrap;">
                        <span style="font-weight:600;">${displayId}</span> 
                        ${propIcon} 
                        ${appIcon}
                    </div>
                    <span>${isChecked}</span>
                </div>`;
    }).join('');
    
    document.getElementById('inputPageInfo').innerText = `${INPUT_PAGE} / ${totalPages}`;
    if (div) div.scrollTop = currentScroll;
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
function formatCoilInfo(data) {
    if (!data) return '';
    const grade = data['GRADE'] || '---';
    const thick = parseFloat(data['target_thick'] || 0).toFixed(2);
    // Nếu chiều rộng là số nguyên thì bỏ .00
    let width = parseFloat(data['target_width'] || 0);
    width = Number.isInteger(width) ? width : width.toFixed(2);
    let weightVal = parseFloat(data['weight']) || 0;
    const weight = weightVal.toLocaleString('vi-VN');
    const slab = data['slab_grade'] || '---';
    return `MVT:  ${thick}x${width} ${grade} | Mẻ: ${slab} `;
}

function updateCombinedNote() {
    const nSurf = document.getElementById('txtNoteSurf').value.trim();
    const nGeo = document.getElementById('txtNoteGeo').value.trim();
    const nProp = document.getElementById('txtNoteProp').value.trim();
    const nApp = document.getElementById('txtNoteApp').value.trim();

    let arr = [];
    if (nSurf) arr.push(nSurf);
    if (nGeo) arr.push(nGeo);
    if (nProp) arr.push(nProp);
    if (nApp) arr.push(nApp);

    document.getElementById('txtInputNote').value = arr.join(', ');
}
// Hàm chọn cuộn để nhập liệu
function selectInputCoil(id) {
    CURRENT_INPUT_COIL = id;
    
    // 1. Lấy dữ liệu ngay lập tức từ biến toàn cục (RAM) -> KHÔNG CÓ ĐỘ TRỄ
    const coilData = RADAR_DATA[id] || {};
    let noteStr = coilData['note_qc'] || '';
    let noteObj = {};
    try { noteObj = JSON.parse(noteStr); } catch(e) { noteObj = { app: noteStr }; }
	SESSION_SNAPSHOT['original_notes'] = noteObj;
    let thickPass = coilData['is_thick_pass'] !== undefined ? coilData['is_thick_pass'] : -1;
    
    const rPass = document.getElementById('radioThickPass');
    const rFail = document.getElementById('radioThickFail');
    if (rPass && rFail) {
        rPass.checked = false; 
        rFail.checked = false; 
        if (thickPass === 1) rPass.checked = true;
        else if (thickPass === 0) rFail.checked = true;
    }

    // Đổ dữ liệu vào 4 ô chi tiết
    document.getElementById('txtNoteSurf').value = noteObj.surf || '';
    document.getElementById('txtNoteGeo').value = noteObj.geo || '';
    document.getElementById('txtNoteProp').value = noteObj.prop || '';
    document.getElementById('txtNoteApp').value = noteObj.app || '';

    // Cập nhật ô Tổng
    updateCombinedNote();
    let timeStr = coilData['production_date'] || '--';
    timeStr = timeStr.replace('T', ' ').split('.')[0];
    // 2. Nhiệt độ & Tốc độ
    const temp = coilData['Temperature'] ? parseFloat(coilData['Temperature']).toFixed(0) : '--';
    const speed = coilData['Speed'] ? parseFloat(coilData['Speed']).toFixed(2) : '--';
    const elInfo = document.getElementById('lblInputInfo');
    if (elInfo) {
        elInfo.innerText = formatCoilInfo(coilData);
    }
    // 2. Thiết lập dữ liệu Gốc (Tham chiếu - Nét đứt)
    // Backend đã gửi sẵn trong auto_scores ở Bước 1
    ORIGINAL_SNAPSHOT = coilData['auto_scores'] ? JSON.parse(JSON.stringify(coilData['auto_scores'])) : {};
    
    // 3. Thiết lập dữ liệu Hiện tại (Đang sửa - Nét liền)
    INPUT_TEMP_DATA = {};
    INPUT_TEMP_DATA['is_thick_pass'] = thickPass;
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
    SESSION_SNAPSHOT = Object.assign({}, INPUT_TEMP_DATA);
    SESSION_SNAPSHOT['original_notes'] = noteObj;
    const elTime = document.getElementById('lblInputTime');
    if(elTime) elTime.innerText = timeStr;
    // 4. Update UI ngay lập tức
    document.querySelectorAll('.coil-item').forEach(e => e.classList.remove('active'));
    document.getElementById(`in_${id}`)?.classList.add('active');
    document.getElementById('lblInputTemp').innerText = temp;
    document.getElementById('lblInputSpeed').innerText = speed;
    document.getElementById('inputEmpty').style.display = 'none';
    document.getElementById('radarInputArea').style.display = 'grid'; 
    document.getElementById('radarInputArea').style.opacity = '1'; 
    const idXuly = coilData['ID_xuly'] || '';
    // 🌟 LOGIC HIỂN THỊ CỜ SKIN KHÁCH ĐẶT
    document.getElementById('lblInputCoil').innerHTML = idXuly 
            ? `${idXuly} <span style="font-size: 0.6em; color: #64748b; font-weight: normal;">(Gốc: ${id})</span>` 
            : id;
    
    // 5. Vẽ biểu đồ
    drawInteractiveRadars();
    renderActionCenter(id);
}
function updateThickPass() {
    if (document.getElementById('radioThickPass').checked) {
        INPUT_TEMP_DATA['is_thick_pass'] = 1;
    } else if (document.getElementById('radioThickFail').checked) {
        INPUT_TEMP_DATA['is_thick_pass'] = 0;
    }
}
// Hàm reset dữ liệu nhập về gốc (Máy đo)
function resetCurrentInput() {
    if(!CURRENT_INPUT_COIL) return;
    
    if(confirm('Khôi phục về dữ liệu gốc (Máy đo) và LƯU lại?')) {
        // 1. Revert dữ liệu tạm về Gốc (Auto Scores)
        INPUT_TEMP_DATA = ORIGINAL_SNAPSHOT ? JSON.parse(JSON.stringify(ORIGINAL_SNAPSHOT)) : {};

        // 2. ÉP is_thick_pass VỀ -1 (Giá trị mặc định chưa đánh giá)
        INPUT_TEMP_DATA['is_thick_pass'] = -1;

        // 3. Chuẩn bị danh sách tất cả các lỗi để đẩy xuống Database
        const allDefectKeys = [
            ...UNIFIED_KEYS.SURFACE, ...UNIFIED_KEYS.GEO, 
            ...UNIFIED_KEYS.PROP, ...UNIFIED_KEYS.APP
        ];
        
        const cleanScores = {};
        allDefectKeys.forEach(k => {
            cleanScores[k] = INPUT_TEMP_DATA[k] !== undefined ? INPUT_TEMP_DATA[k] : 0;
        });
        cleanScores['is_thick_pass'] = -1;
        const notesToSend = {
            surf: document.getElementById('txtNoteSurf').value.trim(),
            geo: document.getElementById('txtNoteGeo').value.trim(),
            prop: document.getElementById('txtNoteProp').value.trim(),
            app: document.getElementById('txtNoteApp').value.trim()
        };

        showLoading();
        // 3. Gọi API Lưu dữ liệu (Cờ is_reset = true)
        fetch('/save_manual_data', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ 
                coil_id: CURRENT_INPUT_COIL, 
                scores: cleanScores,
                is_reset: true,
                note_dict: notesToSend
            })
        }).then(r=>r.json()).then(d => {
            hideLoading();
            
            // 🛡️ CHỈ XỬ LÝ KHI BACKEND TRẢ VỀ SUCCESS
            if (d.status === 'success') {
                
                // 4. ĐỒNG BỘ RAM LẬP TỨC (Giống hệt nút LƯU)
                if(RADAR_DATA[CURRENT_INPUT_COIL]) {
                    // Ghi đè điểm số mới vào RAM
                    for (const [key, value] of Object.entries(cleanScores)) {
                        RADAR_DATA[CURRENT_INPUT_COIL][key] = value;
                    }
                    RADAR_DATA[CURRENT_INPUT_COIL]['is_thick_pass'] = -1;
                    RADAR_DATA[CURRENT_INPUT_COIL]['note_qc'] = JSON.stringify(notesToSend);
                    
                    // Cập nhật các cờ trạng thái quyết định khóa UI
                    if (d.qc_status) RADAR_DATA[CURRENT_INPUT_COIL]['qc_status'] = d.qc_status;
                    if (d.rework_status !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['rework_status'] = d.rework_status;
                    if (d.mapped_po !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['mapped_po'] = d.mapped_po;
                    if (d.qc_msg !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['qc_msg'] = d.qc_msg;
                    if (d.quality_class !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['quality_class'] = d.quality_class;
                    if (d.prime_status !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['prime_status'] = d.prime_status;
                }
                document.getElementById('radioThickPass').checked = false;
                document.getElementById('radioThickFail').checked = false;
                // 5. CHỐT CUỐI CÙNG: Đồng bộ Snapshot để radar tắt nét đứt đỏ (Xác nhận đã lưu)
                Object.assign(SESSION_SNAPSHOT, INPUT_TEMP_DATA);
                
                // 6. Vẽ lại toàn bộ Giao diện
                calculateSummary();
                renderInputList();
                drawInteractiveRadars();
                renderActionCenter(CURRENT_INPUT_COIL);
                
                alert('Đã khôi phục về gốc thành công!');
            } else {
                alert('❌ Không thể khôi phục: ' + d.msg);
            }
        }).catch(e => {
            hideLoading();
            alert('Lỗi khi lưu Reset: ' + e);
        });
    }
}
// Hàm lưu dữ liệu nhập tay
function saveManualData() {
    if(!CURRENT_INPUT_COIL) return;
    const noteVal = document.getElementById('txtInputNote').value.trim();
    const cleanScores = {};
    const allDefectKeys = [
        ...UNIFIED_KEYS.SURFACE, ...UNIFIED_KEYS.GEO, 
        ...UNIFIED_KEYS.PROP, ...UNIFIED_KEYS.APP
    ];
    
    // 1. Quét các lỗi thông thường: Chỉ lấy những giá trị có sự chênh lệch so với lúc mở bảng
    allDefectKeys.forEach(k => {
        const curVal = INPUT_TEMP_DATA[k] !== undefined ? INPUT_TEMP_DATA[k] : 0;
        const orgVal = SESSION_SNAPSHOT[k] !== undefined ? SESSION_SNAPSHOT[k] : 0;
        if (curVal !== orgVal) {
            cleanScores[k] = curVal;
        }
    });

    // 2. Quét logic Chiều dày: Chỉ gửi nếu có sự thay đổi thực tế
    let thickPassValue = -1;
    if (document.getElementById('radioThickPass').checked) thickPassValue = 1;
    else if (document.getElementById('radioThickFail').checked) thickPassValue = 0;

    const orgThickPass = SESSION_SNAPSHOT['is_thick_pass'] !== undefined ? SESSION_SNAPSHOT['is_thick_pass'] : -1;
    if (thickPassValue !== orgThickPass && thickPassValue !== -1) {
        cleanScores['is_thick_pass'] = thickPassValue;
    }
    const currentNotes = {
        surf: document.getElementById('txtNoteSurf').value.trim(),
        geo: document.getElementById('txtNoteGeo').value.trim(),
        prop: document.getElementById('txtNoteProp').value.trim(),
        app: document.getElementById('txtNoteApp').value.trim()
    };
    
    const origNotes = SESSION_SNAPSHOT['original_notes'] || {};
    const notesToSend = {};

    for (let k in currentNotes) {
        if (currentNotes[k] !== (origNotes[k] || '')) {
            notesToSend[k] = currentNotes[k];
        }
    }
    
    showLoading();
    fetch('/save_manual_data', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ coil_id: CURRENT_INPUT_COIL, scores: cleanScores, note_dict: notesToSend }) 
    }).then(r => r.json()).then(d => {
        hideLoading();
        
        // 🛡️ THÊM RÀNG BUỘC KIỂM TRA SUCCESS TẠI FRONTEND
        if (d.status === 'success') {
            alert(d.msg);
            if(RADAR_DATA[CURRENT_INPUT_COIL]) {
                // 1. Cập nhật Điểm Radar (Đúng)
                for (const [key, value] of Object.entries(cleanScores)) {
                    RADAR_DATA[CURRENT_INPUT_COIL][key] = value;
                }
                
                // 2. VÁ LỖI CHIỀU DÀY: Chỉ update RAM nếu thực sự Frontend có gửi dữ liệu đi
                if (cleanScores['is_thick_pass'] !== undefined) {
                    RADAR_DATA[CURRENT_INPUT_COIL]['is_thick_pass'] = thickPassValue;
                }
                
                // 3. VÁ LỖI GHI CHÚ: Hợp nhất (Merge) Ghi chú trên RAM giống hệt như Python làm trên DB
                let ramNoteObj = {};
                try { 
                    ramNoteObj = JSON.parse(RADAR_DATA[CURRENT_INPUT_COIL]['note_qc'] || '{}'); 
                } catch(e) {}
                for(let k in notesToSend) { 
                    ramNoteObj[k] = notesToSend[k]; 
                }
                RADAR_DATA[CURRENT_INPUT_COIL]['note_qc'] = JSON.stringify(ramNoteObj);
                RADAR_DATA[CURRENT_INPUT_COIL]['IS_CHECKED'] = 1;
                if (d.updated_at) {
                    RADAR_DATA[CURRENT_INPUT_COIL]['updated_at'] = d.updated_at;
                }
                
                // --- ĐỒNG BỘ CÁC CỜ TRẠNG THÁI KHÁC (Giữ nguyên) ---
                if (d.qc_status) RADAR_DATA[CURRENT_INPUT_COIL]['qc_status'] = d.qc_status;
                if (d.rework_status !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['rework_status'] = d.rework_status;
                if (d.mapped_po !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['mapped_po'] = d.mapped_po;
                if (d.qc_msg !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['qc_msg'] = d.qc_msg;
                if (d.quality_class !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['quality_class'] = d.quality_class;
                if (d.prime_status !== undefined) RADAR_DATA[CURRENT_INPUT_COIL]['prime_status'] = d.prime_status;
            }
            
            Object.assign(SESSION_SNAPSHOT, INPUT_TEMP_DATA);
			SESSION_SNAPSHOT['original_notes'] = currentNotes;
            renderInputList();
            drawInteractiveRadars();
            calculateSummary(); 
            renderActionCenter(CURRENT_INPUT_COIL);
        } else {
            // Nếu lưu thất bại tại DB, thông báo lỗi và KHÔNG cập nhật RAM để tránh đánh lừa người dùng
            alert('❌ Không thể lưu vào hệ thống: ' + d.msg);
        }
    }).catch(e => {
        hideLoading();
        alert('❌ Lỗi kết nối mạng: ' + e);
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

    // --- TÍNH TOÁN VÀNH ĐAI GIỚI HẠN TỪ TDC ---
    const coil = RADAR_DATA[CURRENT_INPUT_COIL] || {};
    const limits = coil.tdc_limits || {};
    // Nếu TDC quy định giới hạn -> lấy số đó. Nếu TDC không nhắc đến -> Mặc định là 1 (C1: Phải hoàn hảo)
    const limitMaxData = keys.map(k => limits[k] !== undefined ? limits[k].max : 1);
    const limitMinData = keys.map(k => limits[k] !== undefined ? limits[k].min : 0);

    return new Chart(ctx, {
        type: 'radar',
        data: {
            labels: labels,
            datasets: [
                // 1. VIỀN TDC MAX (Đứt nét - Vẽ dưới cùng)
                {
                    label: 'Giới hạn TDC Max',
                    data: limitMaxData,
                    borderColor: '#16a34a',
                    borderWidth: 2,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: false, // Không tô
                    order: 4
                },
                // 2. VIỀN TDC MIN (Tô nền xanh nhạt bao quát dải TDC)
                {
                    label: 'Giới hạn TDC Min',
                    data: limitMinData,
                    borderColor: '#16a34a', // Thêm viền xanh cho min để tạo thành 1 cái "ống"
                    borderWidth: 2,
                    borderDash: [5, 5],
                    pointRadius: 0,
                    fill: '-1', // Đổ màu lên dính vào TDC Max
                    backgroundColor: 'rgba(22, 163, 74, 0.15)', // Tăng độ đậm lên một xíu cho rõ
                    order: 3
                },
                // 3. ĐƯỜNG ĐIỂM GỐC (Màu xám)
                {
                    label: 'Gốc (Máy đo)',
                    data: originalData,
                    borderColor: '#94a3b8',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false, // <--- QUAN TRỌNG: Tắt tô nền
                    backgroundColor: 'transparent',
                    order: 2
                },
                // 4. ĐƯỜNG ĐIỂM THỰC TẾ ĐANG SỬA (Chỉ giữ lại đỉnh/viền)
                {
                    label: 'Đang sửa', 
                    data: currentData,
                    borderColor: color, // Màu xanh dương/đỏ/tím tùy panel
                    borderWidth: 3,
                    // borderDash: [8, 6], // (Tùy chọn) Bạn có thể xóa dòng này để đường cuộn là nét liền cho dễ nhìn
                    pointBackgroundColor: 'white',
                    pointBorderColor: (ctx) => {
                         const index = ctx.dataIndex;
                         const key = keys[index];
                         return (INPUT_TEMP_DATA[key] != ORIGINAL_SNAPSHOT[key]) ? '#dc2626' : color; 
                    },
                    pointRadius: 5,
                    pointHoverRadius: 8,
                    fill: false, // <--- QUAN TRỌNG NHẤT: Bỏ hoàn toàn vùng xanh đậm che mắt
                    backgroundColor: 'transparent',
                    order: 1
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
                        color: (c) => { 
                            const key = keys[c.index];
                            const val = INPUT_TEMP_DATA[key] || 0;
                            const org = ORIGINAL_SNAPSHOT[key] || 0;
                            return (val != org) ? '#dc2626' : '#334155';
                        }
                    }
                }
            },
           plugins: {
                // Ẩn 2 cái label phụ của vành đai đi cho đỡ rác Tooltip
                legend: { 
                    display: false,
                    labels: { filter: function(item, chart) { return !item.text.includes('Tâm'); } }
                }, 
                tooltip: {
                    enabled: true,
                    backgroundColor: 'rgba(0,0,0,0.8)',
                    titleFont: { size: 14 },
                    bodyFont: { size: 13 },
                    padding: 10,
                    displayColors: false, 
                    callbacks: {
                        label: function(context) {
                            if (context.dataset.label === 'Tâm') return null; // Ẩn khỏi Tooltip
                            return `${context.dataset.label}: C${context.raw}`;
                        },
                        afterLabel: function(context) {
                            if (context.dataset.label !== 'Đang sửa') return '';
                            if (!CURRENT_INPUT_COIL || !RADAR_DATA[CURRENT_INPUT_COIL]) return '';
                            const index = context.dataIndex;
                            const key = keys[index]; 
                            const rawInfo = RADAR_DATA[CURRENT_INPUT_COIL].raw_data || {};
                            const val = rawInfo[key];
                            if (val !== undefined && val !== null && val !== '') {

                                if (Array.isArray(val)) {
                                    return val;
                                }
                            
                                const displayVal = (typeof val === 'number') ? `Thực tế: ${val.toFixed(3)}` : val;
                                return ` ${displayVal}`;
                            }
                            return ''; 
                        }
                    }
                }
            },
            // --- 2. LOGIC CLICK VÀO TÊN LỖI ---
            onClick: (e, activeElements, chart) => {
                const coil = RADAR_DATA[CURRENT_INPUT_COIL];
                if (coil) {
                    const isTerminal = (coil.rework_status === 'FINAL' || coil.qc_status === 'PASS' || 
                                        (coil.rework_status && coil.rework_status !== 'NULL' && !coil.ID_xuly));
                    // if (isTerminal) return; // Thoát ngay lập tức, không mở popup sửa điểm
                }
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
		const s = RADAR_DATA[coilId] || {};
        const idXuly = s['ID_xuly'] || '';
        const displayId = idXuly ? `${idXuly}<br><small style="color:#64748b; font-weight:normal; font-size: 0.8em;">Gốc: ${coilId}</small>` : coilId;
        return `<tr>
            <td><b>${start + i + 1}</b></td>
            <td style="font-weight:600">${displayId}</td>
            
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
    document.getElementById('modalList').innerHTML = MODAL_FILT.slice(start,start+50).map(c=>{
        // THÊM LOGIC ĐỌC ID_XULY CHO LIST TRONG MODAL
        const dataC = RADAR_DATA[c] || {};
        const idxC = dataC['ID_xuly'] || '';
        const dispC = idxC ? `${idxC}<br><small style="font-weight:normal;color:#94a3b8">Gốc: ${c}</small>` : c;
        
        return `<div class="coil-item" id="c_${c}" onclick="selectCoil('${c}')"><span style="line-height:1.2">${dispC}</span> <small>▶</small></div>`;
    }).join('');
    document.getElementById('modalPageInfo').innerText=`${MODAL_PAGE}/${Math.ceil(MODAL_FILT.length/50)}`;
}
function selectCoil(id){
    document.querySelectorAll('.coil-item').forEach(e=>e.classList.remove('active'));
    document.getElementById(`c_${id}`)?.classList.add('active');
    document.getElementById('emptyView').style.display='none';
    document.getElementById('radarView').style.display='flex';
    const d = RADAR_DATA[id] || {};
	const idXuly = d['ID_xuly'] || '';
    const displayTitle = idXuly ? `${idXuly} (Gốc: ${id})` : id;
	document.getElementById('modalTitle').innerHTML = `Chi tiết cuộn: <span style="color:#2563eb">${displayTitle}</span>`;
    let timeStr = d['production_date'] || '--';
    timeStr = timeStr.replace('T', ' ').split('.')[0];
    const qual = d['quality_level'] || '---';
    const temp = d['Temperature'] ? parseFloat(d['Temperature']).toFixed(0) : '--';
    const speed = d['Speed'] ? parseFloat(d['Speed']).toFixed(2) : '--';
    document.getElementById('modalStats').style.display = 'flex'; 
    document.getElementById('valModalQual').innerText = qual;
    document.getElementById('valModalTemp').innerText = temp;
    document.getElementById('valModalSpeed').innerText = speed;
    const elInfo = document.getElementById('valModalInfo');
    if (elInfo) {
        elInfo.innerText = formatCoilInfo(d);
    }
    const elTime = document.getElementById('valModalTime');
    if(elTime) elTime.innerText = timeStr;
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
function hideLoading(){
    document.getElementById('loadingOverlay').style.display='none';
    window.MY_LAST_ACTION_TIME = Date.now(); // Ghi nhận thời điểm bạn vừa thao tác xong
}
function resetFilters() { 
    if(document.getElementById('f_qclass')) document.getElementById('f_qclass').value='ALL'; 
    if(document.getElementById('f_pstatus')) document.getElementById('f_pstatus').value='ALL'; 
    if(document.getElementById('f_rework')) document.getElementById('f_rework').value='ALL'; 
    if(document.getElementById('f_qcstatus')) document.getElementById('f_qcstatus').value='ALL'; // Thêm reset cho lọc mới
    
    document.getElementById('s_full').value=''; 
    if(document.getElementById('s_order_sum')) document.getElementById('s_order_sum').value='';
    applyFilters();
}
function filterSummaryTable(type) {
    resetFilters();
    applyFilters();
}

function getRawDetailString(coilId, key) {
    if (!coilId || !RADAR_DATA[coilId] || !RADAR_DATA[coilId].raw_data) {
        return null; 
    }
    const val = RADAR_DATA[coilId].raw_data[key];

    // --- THÊM CHECK ARRAY Ở ĐÂY ---
    if (Array.isArray(val)) {
        return val; // Trả thẳng mảng ra để ChartJS tự xuống dòng
    }
    // ------------------------------

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
    const currentCa = document.getElementById('globalCaSelect') ? document.getElementById('globalCaSelect').value : 'ALL';
    const dStart = document.getElementById('globalDateStart').value;
    const dEnd = document.getElementById('globalDateEnd').value;
    const coilIds = document.getElementById('globalCoilIds') ? document.getElementById('globalCoilIds').value.trim() : '';
    const orderIds = document.getElementById('globalOrderIds') ? document.getElementById('globalOrderIds').value.trim() : '';
    // Tạo một form ẩn để submit bằng phương thức POST
    const form = document.createElement('form');
    form.method = 'POST';
    // Submit vào đúng trang hiện tại (lấy theo pathname để loại bỏ URL params cũ)
    form.action = window.location.pathname; 

    const params = {
        'factory': factory,
        'grade': grade,
        'Ca': currentCa,
        'start_date': dStart,
        'end_date': dEnd,
        'coil_ids': coilIds,
        'order_ids': orderIds
    };

    // Tạo các thẻ input ẩn cho từng param
    for (const key in params) {
        if (params.hasOwnProperty(key)) {
            const hiddenField = document.createElement('input');
            hiddenField.type = 'hidden';
            hiddenField.name = key;
            hiddenField.value = params[key];
            form.appendChild(hiddenField);
        }
    }

    document.body.appendChild(form);
    form.submit();
}
function copyFilteredData() {
    if (!CURRENT_VIEW_LIST || CURRENT_VIEW_LIST.length === 0) {
        alert("Không có dữ liệu nào để copy!");
        return;
    }
    
    // 1. Cập nhật Header: Thêm TxW, Nhóm, Order, TDC Code vào danh sách cột
    let excelData = "Cuộn\tMác thép\tTxW\tKL (Tấn)\tNhóm\tThương Mại\tHạng\tGia Công\tOrder\tTDC Code\tLỗi\tGhi chú\n";

    CURRENT_VIEW_LIST.forEach(id => {
        const s = RADAR_DATA[id] || {};
        const idXuly = s['ID_xuly'] || '';
        const displayId = idXuly ? `${idXuly} (Gốc: ${id})` : id;
        
        const grade = s['GRADE'] || '---';
        const weight = s['weight'] ? (s['weight']/1000).toFixed(2) : '0.00';
        const qClass = s['quality_class'] || '---';
        const pStatus = s['prime_status'] || '---';
        const rStatus = s['rework_status'] || '---';
        
        // --- CÁC BIẾN MỚI ĐƯỢC THÊM VÀO ---
        // Xử lý TxW (Độ dày x Khổ rộng)
        let thick = parseFloat(s['target_thick']) || 0;
        if (thick === 0) {
            thick = parseFloat(s['TARGET_LV2']) || 0;
        }
        let width = parseFloat(s['target_width']) || 0;
        let txw = '---';
        if (thick > 0 || width > 0) {
            let thickDisplay = thick.toFixed(2);
            let widthDisplay = Number.isInteger(width) ? width : width.toFixed(1);
            txw = `${thickDisplay}x${widthDisplay}`;
        }

        // Lấy Nhóm, Order, TDC Code
        const nhom = s['Nhom'] || '-';
        const orderNum = s['original_order'] || '---';
        const tdcCode = s['tdc_code'] || '---';
        // ----------------------------------

        // Lấy tin nhắn qc_msg, xóa dấu xuống dòng/tab để không bị vỡ cột trong Excel
        const qcMsg = (s['qc_msg'] || '').toString().replace(/[\n\r\t]/g, ' ');
        
        let noteStr = s['note_qc'] || '';
        let note = noteStr.toString().replace(/[\n\r\t]/g, ' '); 
        try {
            let obj = JSON.parse(noteStr);
            let arr = [];
            if (obj.surf) arr.push(obj.surf);
            if (obj.geo) arr.push(obj.geo);
            if (obj.prop) arr.push(obj.prop);
            if (obj.app) arr.push(obj.app);
            note = arr.join(', ').replace(/[\n\r\t]/g, ' ');
        } catch(e) {}

        // 2. Ghép dòng Excel: Chèn các biến mới vào chuỗi output theo đúng thứ tự Header
        excelData += `${displayId}\t${grade}\t${txw}\t${weight}\t${nhom}\t${qClass}\t${pStatus}\t${rStatus}\t${orderNum}\t${tdcCode}\t${qcMsg}\t${note}\n`;
    });

    navigator.clipboard.writeText(excelData).then(() => {
        alert(`✅ Đã copy ${CURRENT_VIEW_LIST.length} dòng!`);
    }).catch(err => { alert("❌ Lỗi copy"); });
}
function resetGlobalDate() {
    document.getElementById('globalDateStart').value = '';
    document.getElementById('globalDateEnd').value = '';
    
    if(document.getElementById('globalCoilIds')) {
        document.getElementById('globalCoilIds').value = '';
    }
    if(document.getElementById('globalOrderIds')) {
        document.getElementById('globalOrderIds').value = '';
    }
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
    
    // Chỉ cập nhật dropdown nếu trên URL thực sự có tham số 'factory'
    const factoryParam = urlParams.get('factory');
    if (factoryParam) {
        const factorySelect = document.getElementById('globalFactorySelect');
        if(factorySelect) factorySelect.value = factoryParam;
    }

    // Tương tự cho Mác thép
    const gradeParam = urlParams.get('grade'); 
    if (gradeParam) {
        const select = document.getElementById('globalGradeSelect');
        if(select) {
            select.setAttribute('data-current', gradeParam); 
            select.value = gradeParam;
        }
    }

    loadGradeList();
    loadPreviewOrderList();
    startAutoSync();
});
// --- Trong file qlcl.js ---

function quickSetGroupC1(groupType) {
    if (!CURRENT_INPUT_COIL) {
        alert("Vui lòng chọn cuộn trước khi thao tác!");
        return;
    }
    const coil = RADAR_DATA[CURRENT_INPUT_COIL];
    if (coil) {
        const isTerminal = (coil.rework_status === 'FINAL' || coil.qc_status === 'PASS' || 
                            (coil.rework_status && coil.rework_status !== 'NULL' && !coil.ID_xuly));
        /* (Đang comment để test)
        if (isTerminal) {
            alert("Cuộn thép đã chốt phân cấp hoặc đang xử lý, không được phép sửa điểm!");
            return;
        }
        */
    }

    // --- XỬ LÝ NHÓM BỀ MẶT ---
    if (groupType === 'SURFACE') {
        const targetKeys = [...KEYS.SURFACE_MANUAL, ...KEYS.SURFACE_AUTO];
        
        targetKeys.forEach(key => {
            // Lấy điểm GỐC (từ auto_scores / Máy đo trả về)
            const orgVal = ORIGINAL_SNAPSHOT[key] || 0; 
            
            // Logic: Nếu lỗi quá nặng (C4, C5, C6) -> Chỉ cho phép châm chước xuống C3
            if (orgVal >= 4) {
                INPUT_TEMP_DATA[key] = 3;
            } 
            // Nếu lỗi nhẹ hoặc không có lỗi (C0, C1, C2, C3) -> Xóa sạch về C1
            else {
                INPUT_TEMP_DATA[key] = orgVal; 
            }
        });
    } 
    // --- XỬ LÝ NHÓM NGOẠI QUAN (Giữ nguyên ép về 1) ---
    else if (groupType === 'APP') {
        const targetKeys = KEYS.APP_MANUAL;
        targetKeys.forEach(key => {
            INPUT_TEMP_DATA[key] = 1; 
        });
    }

    // Vẽ lại biểu đồ để cập nhật UI ngay lập tức
    drawInteractiveRadars(); 
}
function openExportModal() {
    document.getElementById('exportExcelModal').style.display = 'flex';
    
    // Tạo ngày hôm nay nhưng ép giờ từ 00:00 đến 23:59
    const today = new Date();
    const pad = (n) => n.toString().padStart(2, '0');
    const formatLocal = (d) => `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
    
    const startOfDay = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 0, 0);
    const endOfDay = new Date(today.getFullYear(), today.getMonth(), today.getDate(), 23, 59);

    document.getElementById('expStartDate').value = formatLocal(startOfDay);
    document.getElementById('expEndDate').value = formatLocal(endOfDay);
}

function closeExportModal() {
    document.getElementById('exportExcelModal').style.display = 'none';
}

function executeExportExcel() {
    const factory = document.getElementById('expFactory').value;
    const startDate = document.getElementById('expStartDate').value;
    const endDate = document.getElementById('expEndDate').value;
    const rawIds = document.getElementById('expCoilIds').value.trim();
    
    // Tách chuỗi ID thành mảng
    const coilIds = rawIds ? rawIds.split(/[\s,]+/).filter(id => id.length > 0) : [];

    showLoading(); // Hàm loading có sẵn của bạn
    
    fetch('/api/export_excel_qc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            factory: factory,
            start_date: startDate,
            end_date: endDate,
            coil_ids: coilIds
        })
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(err => { throw new Error(err.msg || 'Lỗi server'); });
        }
        return response.blob(); // Phải nhận định dạng blob cho file Excel
    })
    .then(blob => {
        hideLoading();
        closeExportModal();
        
        // Tạo link ẩn để tải file
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        // Đặt tên file có timestamp
        const timestamp = new Date().toISOString().replace(/[:.]/g, '-').substring(0, 19);
        a.download = `BaoCao_QC_${factory}_${timestamp}.xlsx`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
    })
    .catch(error => {
        hideLoading();
        alert('❌ Lỗi xuất Excel: ' + error.message);
    });
}
let lastSyncTimestamp = Date.now() / 1000; // Lưu thời điểm tải trang
let isSyncing = false;

function startAutoSync() {
    // Hỏi thăm mỗi 15 giây (Tốc độ SX là 1.5 - 4p, nên 15s là quá nhanh và an toàn)
    setInterval(() => {
        if (isSyncing) return; 
        
        fetch('/api/check_new_data')
            .then(r => r.json())
            .then(status => {
                if (status.timestamp > lastSyncTimestamp) {
                    isSyncing = true;
                    let localDate = new Date(lastSyncTimestamp * 1000);
                    let safeDate = new Date(localDate.getTime() - (localDate.getTimezoneOffset() * 60000) - 5000);
                    let lastTimeStr = safeDate.toISOString().replace('T', ' ').substring(0, 19);
                    
                    const currentFactory = document.getElementById('globalFactorySelect')?.value || 'ALL';
                    const currentGrade = document.getElementById('globalGradeSelect')?.value || 'ALL';
                    const currentCa = document.getElementById('globalCaSelect')?.value || 'ALL';
                    const dStart = document.getElementById('globalDateStart')?.value || '';
                    const dEnd = document.getElementById('globalDateEnd')?.value || '';
                    const coilIds = document.getElementById('globalCoilIds')?.value.trim() || '';
                    const orderIds = document.getElementById('globalOrderIds')?.value.trim() || ''; 
                    const url = `/api/get_latest_coils?since=${lastTimeStr}&factory=${currentFactory}&grade=${currentGrade}&Ca=${currentCa}&start_date=${dStart}&end_date=${dEnd}&coil_ids=${encodeURIComponent(coilIds)}&order_ids=${encodeURIComponent(orderIds)}`;
                    fetch(url)
                        .then(r => r.json())
                        .then(res => {
                            if (res.status === 'success' && Object.keys(res.data).length > 0) {
                                
                                // 3. Gộp dữ liệu mới vào RAM (RADAR_DATA)
                                for (let cid in res.data) {
                                    // BẢO VỆ UX: Nếu cuộn này đang được chọn để Nhập Liệu trên màn hình
                                    // -> Bỏ qua không update ngầm để tránh làm mất dữ liệu QC đang gõ tay dở dang.
                                    if (cid === CURRENT_INPUT_COIL) {
                                        const serverData = res.data[cid];
                                        if (serverData && serverData.updated_at !== RADAR_DATA[cid].updated_at) {
                                            
                                            // 1. Cập nhật các cờ trạng thái khóa UI
                                            RADAR_DATA[cid].qc_status = serverData.qc_status;
                                            RADAR_DATA[cid].rework_status = serverData.rework_status;
                                            RADAR_DATA[cid].mapped_po = serverData.mapped_po;
                                            RADAR_DATA[cid].qc_msg = serverData.qc_msg;
                                            RADAR_DATA[cid].quality_class = serverData.quality_class;
                                            RADAR_DATA[cid].prime_status = serverData.prime_status;
                                            RADAR_DATA[cid].updated_at = serverData.updated_at;
                                            
                                            let needRedraw = false;
                                            
                                            // 🌟 SỬA LỖI LOGIC: Dùng mảng UNIFIED_KEYS để chủ động đi tìm điểm
                                            const allDefectKeys = [
                                                ...UNIFIED_KEYS.SURFACE, ...UNIFIED_KEYS.GEO, 
                                                ...UNIFIED_KEYS.PROP, ...UNIFIED_KEYS.APP
                                            ];
                                            
                                            // 2. MERGE ĐIỂM SỐ TRỰC TIẾP
                                            allDefectKeys.forEach(k => {
                                                const sVal = serverData[k] !== undefined ? serverData[k] : 0;
                                                const origVal = SESSION_SNAPSHOT[k] !== undefined ? SESSION_SNAPSHOT[k] : 0;
                                                const tempVal = INPUT_TEMP_DATA[k] !== undefined ? INPUT_TEMP_DATA[k] : 0;

                                                // Nếu Server có điểm khác với Gốc -> Người A vừa sửa
                                                if (sVal !== origVal) {
                                                    // Nếu Người B chưa đụng tay vào điểm này -> Tự động nhận điểm của A
                                                    if (tempVal === origVal) {
                                                        INPUT_TEMP_DATA[k] = sVal;
                                                        SESSION_SNAPSHOT[k] = sVal; // Chốt mốc mới để B không gửi đè lại
                                                        RADAR_DATA[cid][k] = sVal;  
                                                        needRedraw = true;
                                                    }
                                                }
                                            });
                                            
                                            // 3. MERGE CHIỀU DÀY (is_thick_pass)
                                            const sThick = serverData['is_thick_pass'];
                                            if (sThick !== undefined && sThick !== SESSION_SNAPSHOT['is_thick_pass']) {
                                                if (INPUT_TEMP_DATA['is_thick_pass'] === SESSION_SNAPSHOT['is_thick_pass']) {
                                                    INPUT_TEMP_DATA['is_thick_pass'] = sThick;
                                                    SESSION_SNAPSHOT['is_thick_pass'] = sThick;
                                                    RADAR_DATA[cid]['is_thick_pass'] = sThick;
                                                    if (sThick === 1) document.getElementById('radioThickPass').checked = true;
                                                    else if (sThick === 0) document.getElementById('radioThickFail').checked = true;
                                                }
                                            }
                                            
                                            // 4. MERGE GHI CHÚ
                                            RADAR_DATA[cid].note_qc = serverData.note_qc || '';
                                            let sNoteObj = {};
                                            try { sNoteObj = JSON.parse(serverData.note_qc || '{}'); } catch(e) {}
                                            
                                            const curNoteObj = SESSION_SNAPSHOT['original_notes'] || {};
                                            ['surf', 'geo', 'prop', 'app'].forEach(t => {
                                                const el = document.getElementById('txtNote' + t.charAt(0).toUpperCase() + t.slice(1));
                                                if (el) {
                                                    const serverTxt = sNoteObj[t] || '';
                                                    const origTxt = curNoteObj[t] || '';
                                                    const uiTxt = el.value.trim();
                                                    
                                                    // Nếu A gõ thêm chữ, mà B chưa gõ gì vào ô này -> Cập nhật màn hình cho B
                                                    if (serverTxt !== origTxt && uiTxt === origTxt) {
                                                        el.value = serverTxt;
                                                        curNoteObj[t] = serverTxt; // Chốt gốc
                                                        // Nháy xanh lá cây để KCS B biết ô này vừa có người cập nhật ngầm
                                                        el.style.backgroundColor = '#dcfce7'; 
                                                        setTimeout(() => el.style.backgroundColor = '#f8fafc', 1500);
                                                    }
                                                }
                                            });
                                            updateCombinedNote();
                                            
                                            // 5. Cập nhật hình ảnh Radar
                                            if (needRedraw) drawInteractiveRadars();
                                            renderActionCenter(cid);
                                        }
                                        continue; 
                                    }
                                    RADAR_DATA[cid] = res.data[cid];
                                }
                                                                
                                // Cập nhật lại thời gian chốt sổ
                                lastSyncTimestamp = status.timestamp;
                                
                                // 4. Cập nhật giao diện 

                                // Lưu tọa độ cuộn của toàn bộ trang web (dành cho Bảng Tổng Hợp)
                                const currentWindowScroll = window.scrollY;
                                calculateSummary(true); // 🌟 Truyền true để KHÔNG reset FULL_PAGE
                                renderInputList(); 
                                // Trả lại tọa độ cuộn cho Bảng Tổng hợp
                                window.scrollTo(0, currentWindowScroll);
                                console.log("🔥 Tự động tải thành công cuộn mới!");
                            }
                            isSyncing = false;
                        }).catch(() => isSyncing = false);
                }
            }).catch(err => console.log("Lỗi check sync", err));
            
    }, 5000); // 15000ms = 15 giây
}
function importNotesExcel() {
    const fileInput = document.getElementById('fileImportNotes');
    const file = fileInput.files[0];
    
    if (!file) {
        alert("⚠️ Vui lòng chọn file Excel trước khi Upload!");
        return;
    }

    const formData = new FormData();
    formData.append('file', file);

    showLoading(); // Hàm loading đã có sẵn trong JS của bạn
    
    fetch('/api/import_notes_excel', {
        method: 'POST',
        body: formData // Fetch tự động set header Content-Type multipart/form-data
    })
    .then(async response => {
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("text/html") !== -1) {
            throw new Error("Hệ thống đang cập nhật, vui lòng tải lại trang sau 1-2 phút để kiểm tra!");
        }
        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.msg || 'Lỗi xử lý từ máy chủ');
        }
        return response.json();
	})
    .then(data => {
        hideLoading();
        if (data.status === 'success') {
            alert(`✅ ${data.msg}`);
            fileInput.value = ''; // Xoá file đã chọn
            if (data.updated_data) {
                for (let inputId in data.updated_data) {
                    let newNote = data.updated_data[inputId];
                    let coilId = null;

                    // Tìm ID gốc của cuộn (Vì Excel có thể nhập coil_id hoặc ID_xuly)
                    if (RADAR_DATA[inputId]) {
                        coilId = inputId;
                    } else {
                        coilId = Object.keys(RADAR_DATA).find(k => RADAR_DATA[k].ID_xuly === inputId);
                    }

                    // Nếu tìm thấy cuộn trên bộ nhớ, tiến hành vá dữ liệu
                    if (CURRENT_INPUT_COIL === coilId) {
                            const noteInput = document.getElementById('txtInputNote');
                            if (noteInput) {
                                noteInput.value = newNote;
                                noteInput.style.backgroundColor = '#dcfce7'; 
                                setTimeout(() => noteInput.style.backgroundColor = 'white', 500);
                            }

                            // [QUAN TRỌNG]: Phải đồng bộ cả 4 ô note nhỏ để tránh bị ghi đè khi bấm LƯU.
                            // Vì Excel là text thuần, ta đẩy tạm vào ô Ngoại quan (app) giống cơ chế fallback
                            document.getElementById('txtNoteSurf').value = '';
                            document.getElementById('txtNoteGeo').value = '';
                            document.getElementById('txtNoteProp').value = '';
                            document.getElementById('txtNoteApp').value = newNote; // Đẩy Note Excel vào đây
                        }
                    }
                // Render lại bảng Tổng hợp để hiển thị ghi chú mới
                renderFullTable();
            }    // Reload trang để hiển thị Note mới trên bảng
        } else {
            alert(`❌ Lỗi: ${data.msg}`);
        }
    })
    .catch(error => {
        hideLoading();
        alert('❌ Lỗi kết nối Server: ' + error);
    });
}
let ACTIVE_QC_COIL_ID = null;

/**
 * Lắng nghe sự kiện thay đổi của Dropdown 2.2.1
 * Tự động chuyển luồng hiển thị sang bước tiếp theo nếu không thể xử lý cơ học
 */
function onReworkDropdownChange() {
    const val = document.getElementById('ddlPhysicalProcess').value;
    const btnConfirm = document.getElementById('btnConfirmRework');
    const step2_PO = document.getElementById('pnlStep2_PO');
    const step3_Downgrade = document.getElementById('pnlStep3_Downgrade');

    if (val === 'CANNOT_REWORK') {
        // 🌟 MỞ KHÓA CHO TẤT CẢ: PENDING, PASSNOCHEM, FAILNOCHEM, FAIL
        btnConfirm.style.display = 'none';
        if (step2_PO) step2_PO.style.display = 'flex';
        if (step3_Downgrade) step3_Downgrade.style.display = 'none';
    } else if (val !== 'NULL') {
        // CÁC LỆNH RỚT/XỬ LÝ CƠ HỌC (RCL, SKIN, CXL...)
        btnConfirm.style.display = 'inline-block';
        if (step2_PO) step2_PO.style.display = 'none';
        if (step3_Downgrade) step3_Downgrade.style.display = 'none';
    } else {
        btnConfirm.style.display = 'inline-block';
        if (step2_PO) step2_PO.style.display = 'none';
        if (step3_Downgrade) step3_Downgrade.style.display = 'none';
    }
}
function confirmNoOrderSelected() {
    // Tắt modal Gợi ý PO
    document.getElementById('mdlOrderRecommend').style.display = 'none';
    
    // Step 2 Bế tắc (Không tìm được đơn) -> Mở cánh cửa cuối cùng: Step 3
    document.getElementById('pnlStep3_Downgrade').style.display = 'flex';
}
/**
 * Hàm render lại Action Center khi chọn cuộn trên danh sách
 */
function renderActionCenter(coilId) {
    ACTIVE_QC_COIL_ID = coilId;
    const coil = RADAR_DATA[coilId];
    const actionCenter = document.getElementById('qcActionCenter');
    if (!coil || !actionCenter) return;

    actionCenter.style.display = 'block';

    // 1. Lấy dữ liệu trạng thái và FIX LỖI khai báo biến status toàn cục
    const stage = coil.qc_stage;          
    const status = coil.qc_status || 'PENDING'; // 🌟 Đã khai báo an toàn
    const isFailed = (status === 'FAIL' || status === 'FAILNOCHEM');

    const idXuly = coil.ID_xuly || coil.ID_XuLy;
    let reworkStatus = coil.rework_status || "NULL";
    const mappedPo = coil.mapped_po;
    const suggestedPo = coil.suggested_order_map;
    const qcMsg = coil.qc_msg || ''; 
    const isTerminal = (status === 'PASS' || status === 'PASS_LEGACY' || stage === 'FINAL') || 
                       (reworkStatus === 'FINAL' && status !== 'PASSNOCHEM' && status !== 'FAILNOCHEM');
    const weightVal = parseFloat(coil.weight) || 0;
    const lblWeight = document.getElementById('lblUiWeight');
    if (lblWeight) lblWeight.innerText = weightVal.toLocaleString('vi-VN') + ' kg';
    const lblSkinCust = document.getElementById('lblUiSkinCust');
    if (lblSkinCust) {
        lblSkinCust.style.display = (coil.is_skin_required === 1) ? 'inline-block' : 'none';
    }
    if (!coil.original_order || coil.original_order === '---') {
        
        // 1. Dựng thẻ datalist từ biến RAM
        let datalistHtml = `<datalist id="dlOrdersPreview_${coilId}">`;
        PREVIEW_ORDER_LIST.forEach(o => {
            // value là mã Order thật để gọi API, text hiển thị kèm mô tả
            datalistHtml += `<option value="${o.order_id}">${o.desc}</option>`;
        });
        datalistHtml += `</datalist>`;

        // 2. Chèn vào UI
        document.getElementById('lblUiOrder').innerHTML = `
            <div style="display:inline-flex; align-items:center; gap:5px;">
                ${datalistHtml}
                <input type="text" id="inlinePreviewOrder" list="dlOrdersPreview_${coilId}"
                       placeholder="🔍 Chọn/Gõ Order ướm thử..." 
                       title="Click để chọn hoặc gõ mã để lọc nhanh"
                       onchange="triggerInlinePreview(this.value)"
                       style="padding: 2px 8px; border: 1px dashed #f59e0b; border-radius: 4px; outline: none; font-size: 0.9em; color: #d97706; font-weight: bold; width: 150px; background: #fffbeb;">
                <button onclick="document.getElementById('inlinePreviewOrder').value=''; triggerInlinePreview('');" 
                        title="Hủy ướm thử" 
                        style="background:none; border:none; color:#ef4444; cursor:pointer; font-weight:bold; font-size: 1.1em; padding: 0 4px;">✖</button>
            </div>
        `;
    } else {
        document.getElementById('lblUiOrder').innerText = coil.original_order;
    }
    
    const tdcCode = coil.tdc_code || '---';
    const lblUiTdc = document.getElementById('lblUiTdc');
    if (lblUiTdc) {
        lblUiTdc.innerText = tdcCode;
        if (tdcCode !== '---' && tdcCode !== '') {
            lblUiTdc.href = `/tdc_manager?focus_tdc=${encodeURIComponent(tdcCode)}`;
            lblUiTdc.style.pointerEvents = 'auto';
        } else {
            lblUiTdc.href = "#";
            lblUiTdc.style.pointerEvents = 'none';
        }
    }
    document.getElementById('lblSuggestedOrder').innerText = suggestedPo || "---";

    const divQcMsgBox = document.getElementById('divUiQcMsgBox');
    const lblQcMsg = document.getElementById('lblUiQcMsg');
    if (divQcMsgBox && lblQcMsg) {
        if (qcMsg && qcMsg.trim() !== '') {
            lblQcMsg.innerText = qcMsg; divQcMsgBox.style.display = 'flex';
        } else { divQcMsgBox.style.display = 'none'; }
    }
    
    const qClass = coil.quality_class || '';
    const pStatus = coil.prime_status || '';
    const badgeDiv = document.getElementById('divUiQualityBadge');
    const badgeLbl = document.getElementById('lblUiQuality');
    if (badgeDiv && badgeLbl) {
        if (pStatus && pStatus !== 'NULL' && pStatus !== 'None') {
            // Lấy lý do hạ cấp từ RAM (nếu có)
            const downgradeNote = coil.downgrade_reason ? ` (Lý do: ${coil.downgrade_reason})` : '';
            
            badgeLbl.innerText = `${qClass} - ${pStatus}`; 
            badgeDiv.style.display = 'flex';
            
            if (pStatus === 'PRIME') {
                badgeDiv.style.background = '#f0fdf4'; badgeDiv.style.borderColor = '#bbf7d0'; badgeLbl.style.color = '#16a34a';
                badgeDiv.title = 'Hàng loại 1 xuất sắc';
            } else if (pStatus === 'NON_PRIME') {
                badgeDiv.style.background = '#fffbeb'; badgeDiv.style.borderColor = '#fde68a'; badgeLbl.style.color = '#d97706';
                badgeDiv.title = downgradeNote; // Di chuột vào sẽ thấy lý do hạ cấp
            } else if (pStatus === 'SCRAP') {
                badgeDiv.style.background = '#f1f5f9'; badgeDiv.style.borderColor = '#cbd5e1'; badgeLbl.style.color = '#475569';
                badgeDiv.title = downgradeNote; // Di chuột vào sẽ thấy lý do hạ cấp
            }
        } else { 
            badgeDiv.style.display = 'none'; 
        }
    }

    // Cập nhật màu sắc tem trạng thái tổng cho cả FAILNOCHEM và PASSNOCHEM
    const lblStatus = document.getElementById('lblUiStatus');
    if (lblStatus) {
        lblStatus.innerText = status;
        if (status === 'PASS') {
            lblStatus.style.background = "#dcfce7"; lblStatus.style.color = "#15803d";
        } else if (status === 'FAIL') {
            lblStatus.style.background = "#fee2e2"; lblStatus.style.color = "#b91c1c";
        } else if (status === 'FAILNOCHEM') {
            lblStatus.style.background = "#ffedd5"; lblStatus.style.color = "#ea580c"; // Màu cam cảnh báo lỗi sớm
        } else if (status === 'PASSNOCHEM') {
            lblStatus.style.background = "#e0f2fe"; lblStatus.style.color = "#0369a1"; // Màu xanh lam chờ đợi
        } else {
            lblStatus.style.background = "#f1f5f9"; lblStatus.style.color = "#475569";
        }
    }

    const mainControls = document.getElementById('acMainControls');
    const waitMsg = document.getElementById('acWaitMsg');

    const showMessageOnly = (msg, bgColor, textColor) => {
        mainControls.style.display = 'none'; waitMsg.style.display = 'block';
        waitMsg.style.backgroundColor = bgColor || "#f8fafc"; waitMsg.style.color = textColor || "#475569";
        waitMsg.innerHTML = msg;
    };

    const showControlsOnly = () => {
        mainControls.style.display = 'flex'; waitMsg.style.display = 'none';
        const ddl = document.getElementById('ddlPhysicalProcess');
        if (ddl) {
            let optionsHtml = `<option value="NULL">-- 1. Chọn xử lý --</option>
                               <option value="LAY_MAU">🧪 Lấy mẫu Lab</option>`;
            let validOptions = ['NULL', 'LAY_MAU'];

            if (coil.is_skin_required === 1) {
                optionsHtml += `<option value="SKIN_CUST">SKIN Khách đặt</option>`;
                validOptions.push('SKIN_CUST');
            }
            
            // 🌟 LUÔN HIỂN THỊ FULL OPTION CHO TẤT CẢ (PENDING, PASSNOCHEM, FAILNOCHEM, FAIL)
            optionsHtml += `<option value="RCL">Xử lý RCL</option>
                            <option value="SKIN">Xử lý SKIN</option>
                            <option value="CXL">CXL (Xử lý tay)</option>
                            <option value="CANNOT_REWORK">❌ Không thể xử lý</option>`;
            validOptions.push('RCL', 'SKIN', 'CXL', 'CANNOT_REWORK');

            ddl.innerHTML = optionsHtml;
            ddl.value = validOptions.includes(reworkStatus) ? reworkStatus : "NULL";
        }
        if(typeof onReworkDropdownChange === 'function') onReworkDropdownChange();
    };
    const isDowngraded = (pStatus === 'NON_PRIME' || pStatus === 'SCRAP');
    // ========================================================
    // 🌟 4. MÁY TRẠNG THÁI TUẦN TỰ NÂNG CẤP (CHỐNG XUNG ĐỘT)
    // ========================================================
    if (status === 'PASS' && reworkStatus === 'SKIN_CUST') {
        let actionHtml = `<button onclick="confirmCXLComplete('${coilId}')" style="background:#10b981; color:white; border:none; padding:6px 16px; border-radius:4px; font-weight:bold; cursor:pointer;">✅ Xác Nhận Đã Xong</button>`;
        if (!idXuly) {
            showMessageOnly(`<div style="display:flex; justify-content:space-between; width:100%;"><span>⚙️ Đang thực hiện lệnh SKIN Khách đặt. Chờ kết quả...</span>${actionHtml}</div>`, "#e0f2fe", "#0369a1");
            setRadarInputsLockState(coilId, true);
        } else {
            showMessageOnly(`<div style="display:flex; justify-content:space-between; width:100%;"><span>✅ SKIN về <b>(${idXuly})</b>. Đo lại Bề mặt và LƯU!</span>${actionHtml}</div>`, "#fef3c7", "#92400e");
            setRadarInputsLockState(coilId, false, true);
        }
    }
    else if (isTerminal || isDowngraded) {
        let poDisplayText = mappedPo === '0' ? 'Kho tồn kho (MTS)' : (mappedPo === '1' ? '⏳ Chờ SO gắn Order' : mappedPo); 
        let undoBtnHtml = '';
        if ((USER_ROLE === 'admin' || USER_PERMISSIONS.includes('qlcl_manager_undo')) && isDowngraded) {
            undoBtnHtml = `<button onclick="confirmUndoDowngrade('${coilId}')" style="margin-left:15px; padding:6px 14px; background:#ef4444; color:white; border:none; border-radius:6px; cursor:pointer;">🔄 Hoàn tác Hạ cấp</button>`;
        }

        // Tạo khối HTML chứa lý do hạ cấp (nếu có)
        let reasonHtml = coil.downgrade_reason ? `<br><span style="font-size:0.9em; color:#64748b; margin-top:4px; display:inline-block;">📝 Lý do: <b>${coil.downgrade_reason}</b></span>` : '';

        if (pStatus === 'PRIME' || !pStatus || pStatus === 'NULL') {
            showMessageOnly(`✅ ĐẠT CHUẨN. Phân bổ: <b>${poDisplayText}</b>`, "#dcfce7", "#15803d");
        } else if (pStatus === 'NON_PRIME') {
            // Chèn reasonHtml vào sau dòng Phân bổ
            showMessageOnly(`<div style="display:flex; justify-content:space-between; width:100%;"><div>⚠️ Hạ cấp: <b>NON-PRIME</b> <br> <span style="font-size:0.9em;">🏷️ Phân bổ: <b>${poDisplayText}</b></span>${reasonHtml}</div>${undoBtnHtml}</div>`, "#fef3c7", "#92400e");
        } else {
            // SCRAP: Chỉ chèn reasonHtml vào ngay sau tên trạng thái
            showMessageOnly(`<div style="display:flex; justify-content:space-between; width:100%;"><div>🚫 Hạ cấp: <b>${pStatus}</b>${reasonHtml}</div>${undoBtnHtml}</div>`, "#fef2f2", "#b91c1c");
        }
        setRadarInputsLockState(coilId, true);
    }
    else if (status === 'FAIL' && suggestedPo) {
        showMessageOnly(`⏳ Đang chờ SAP phê duyệt chuyển sang Đơn: <b>${suggestedPo}</b>`, "#fef3c7", "#92400e");
        setRadarInputsLockState(coilId, true);
    }
    else if (reworkStatus !== 'NULL' && reworkStatus !== 'FINAL' && reworkStatus !== 'CANNOT_REWORK' && (['LAY_MAU', 'CXL', 'SKIN_CUST'].includes(reworkStatus) || !idXuly || idXuly === '')) {
        // [Nhánh Đang Gia Công]: Tự động hiển thị "Xác nhận đã xong" cho cả LAY_MAU, RCL, SKIN, SKIN_CUST, CXL...
        let reworkName = reworkStatus === 'CXL' ? 'CXL (Xử lý tay)' : (reworkStatus === 'LAY_MAU' ? 'Lấy mẫu Lab' : (reworkStatus === 'SKIN_CUST' ? 'SKIN Khách đặt' : (reworkStatus === 'RCL' ? 'RCL (Sửa biên)' : 'SKIN (Cán nắn)')));
        let actionHtml = `<button onclick="confirmCXLComplete('${coilId}')" style="background:#10b981; color:white; border:none; padding:6px 16px; border-radius:4px; font-weight:bold; cursor:pointer;">✅ Xác Nhận Đã Xong</button>`;
        
        showMessageOnly(`
            <div style="display:flex; align-items:center; justify-content:space-between; width:100%;">
                <span>⚙️ Đang thực hiện lệnh <b>${reworkName}</b>. Chờ kết quả...</span>
                ${actionHtml}
            </div>
        `, "#e0f2fe", "#0369a1");
        
        setRadarInputsLockState(coilId, true);
    }
    else {
        showControlsOnly();
        const returnedFromFactory = (reworkStatus !== 'NULL' && reworkStatus !== 'CANNOT_REWORK' && idXuly);
        setRadarInputsLockState(coilId, false, returnedFromFactory);
    }
}
function confirmCXLComplete(coilId) {
    if (!confirm(`Xác nhận cuộn ${coilId} đã được xử lý xong và sẵn sàng đo lại QC?`)) return;

    showLoading();
    fetch('/api/complete_cxl', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ coil_id: coilId, user: 'QC_User' })
    })
    .then(r => r.json())
    .then(d => {
        hideLoading();
        if (d.status === 'success') {
            alert(d.msg);
            
            // Đồng bộ RAM: Trả rework_status về NULL
            if (RADAR_DATA[coilId]) {
                RADAR_DATA[coilId].rework_status = 'NULL';
            }
            
            // Render lại giao diện (sẽ tự động mở khóa)
            renderActionCenter(coilId);
            renderFullTable();
            renderInputList();
        } else {
            alert('❌ Lỗi: ' + d.msg);
        }
    })
    .catch(e => { hideLoading(); alert('Lỗi: ' + e); });
}    
function setRadarInputsLockState(coilId, isLocked, onlySurface=false) {
    const coil = RADAR_DATA[coilId];
    if (!coil) return;

    // Trạng thái khóa cứng (Cuộn đã chốt FINAL hoặc đã đi RCL/SKIN/SKIN_CUST)
    const isTerminal = (coil.rework_status === 'FINAL' || 
                        (coil.rework_status && coil.rework_status !== 'NULL' && !coil.ID_xuly));
    
    // Nếu là trạng thái Terminal hoặc isLocked truyền vào = true -> Khóa toàn bộ
    // const lockAll = isLocked || isTerminal;
    const lockAll = false;
    // 1. Khóa các input Lab/Cơ Lý cũ (Giữ nguyên)
    const inputs = document.querySelectorAll('.qc-input'); 
    inputs.forEach(input => {
        if (onlySurface) {
            if (input.dataset.group === 'lab') input.disabled = true;
        } else {
            input.disabled = lockAll;
        }
    });

    // 2. KHÓA CÁC NÚT HẠ CẤP (NON-PRIME / SCRAP) (Giữ nguyên)
    const commercialGroup = document.getElementById('acCommercialGroup');
    if (commercialGroup) {
        commercialGroup.style.opacity = lockAll ? "0.5" : "1";
        commercialGroup.style.pointerEvents = lockAll ? "none" : "auto";
    }

    // 3. Khóa Dropdown xử lý nếu đang trong quá trình gia công (Giữ nguyên)
    const ddlRework = document.getElementById('ddlPhysicalProcess');
    if (ddlRework) ddlRework.disabled = lockAll;

    // 🛠️ VÁ THÊM: TÌM VÀ KHÓA CHẶN NÚT LƯU + NÚT RESET GỐC TRÊN GIAO DIỆN CỦA BẠN
    const btnSave = document.querySelector("button[onclick='saveManualData()']");
    const btnReset = document.querySelector("button[onclick='resetCurrentInput()']");
    
    if (btnSave) {
        btnSave.disabled = lockAll;
        btnSave.style.opacity = lockAll ? "0.4" : "1";
        btnSave.style.pointerEvents = lockAll ? "none" : "auto";
        btnSave.style.cursor = lockAll ? "not-allowed" : "pointer";
    }
    if (btnReset) {
        btnReset.disabled = lockAll;
        btnReset.style.opacity = lockAll ? "0.4" : "1";
        btnReset.style.pointerEvents = lockAll ? "none" : "auto";
        btnReset.style.cursor = lockAll ? "not-allowed" : "pointer";
    }
}
function openDowngradeModal(type) {
    document.getElementById('hdnDgActionType').value = type;
    document.getElementById('txtDgReason').value = "";
    
    if (type === 'NON_PRIME') {
        document.getElementById('mdlDgTitle').innerText = "Xác nhận hạ cấp thương mại Non-Prime";
        document.getElementById('btnSubmitDg').style.background = "#f59e0b";
        document.getElementById('mdlDgIcon').innerText = "⚠️";
    } else {
        document.getElementById('mdlDgTitle').innerText = "Xác nhận chuyển loại Thứ phẩm(Loại 2)";
        document.getElementById('btnSubmitDg').style.background = "#475569";
        document.getElementById('mdlDgIcon').innerText = "🗑️";
    }
    document.getElementById('mdlDowngradeConfirm').style.display = 'block';
}

function closeDowngradeModal() {
    document.getElementById('mdlDowngradeConfirm').style.display = 'none';
}
// =====================================================================
// CÁC HÀM BỔ TRỢ KHÓA/MỞ KHÓA RADAR
// =====================================================================
function setInputDisabledState(key, isDisabled) {
    const el = document.getElementById(`input_${key}`) || document.getElementById(`slider_${key}`);
    if (el) {
        el.disabled = isDisabled;
        el.style.backgroundColor = isDisabled ? "#f1f5f9" : "#ffffff";
    }
}

function disableFormInputs(state) {
    const allKeys = [...KEYS.SURFACE_MANUAL, ...KEYS.GEO_MANUAL, ...KEYS.MECH_AUTO, ...KEYS.CHEM_AUTO];
    allKeys.forEach(k => setInputDisabledState(k, state));
}

// =====================================================================
// CÁC HÀM THỰC THI GỌI API TỪ ACTION CENTER
// =====================================================================
function executePhysicalRework() {
    const act = document.getElementById('ddlPhysicalProcess').value;
    if (act === 'NULL' || act === 'CANNOT_REWORK') {
        return alert('Vui lòng chọn một phương án xử lý cơ học thực tế (RCL hoặc SKIN)!');
    }
    
    if (confirm(`Bạn chắc chắn muốn phát lệnh đưa cuộn ${ACTIVE_QC_COIL_ID} đi xử lý hình thức [${act}]?`)) {
        const btnSave = document.querySelector("button[onclick='saveManualData()']");
        if (btnSave) btnSave.disabled = true;
        showLoading();
        fetch('/api/update_rework_status', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ coil_id: ACTIVE_QC_COIL_ID, rework_type: act })
        })
        .then(r => r.json())
        .then(d => {
            hideLoading();
            if (btnSave) btnSave.disabled = false;
            if (d.status === 'success') {
                alert(d.msg);
                RADAR_DATA[ACTIVE_QC_COIL_ID]['rework_status'] = act; // act chính là 'RCL', 'SKIN' hoặc 'SKIN_CUST'
                if (act !== 'LAY_MAU' && act !== 'CANNOT_REWORK') {
                    RADAR_DATA[ACTIVE_QC_COIL_ID]['ID_xuly'] = null; 
                } 
                renderActionCenter(ACTIVE_QC_COIL_ID);
                calculateSummary();
                renderInputList();
            } else {
                alert('❌ Lỗi: ' + d.msg);
            }
        }).catch(e => { hideLoading(); alert('Lỗi kết nối: ' + e); });
    }
}

function submitCommercialDowngrade() {
    const type = document.getElementById('hdnDgActionType').value;
    const reason = document.getElementById('txtDgReason').value.trim();
    
    if (reason === "") return alert("Bắt buộc phải nhập lý do chi tiết để hạ cấp sản phẩm!");
    
    showLoading();
    fetch('/api/downgrade_coil', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ coil_id: ACTIVE_QC_COIL_ID, action_type: type, note: reason })
    })
    .then(r => r.json())
    .then(d => {
        hideLoading();
        closeDowngradeModal();
        if (d.status === 'success') {
            alert(d.msg);
            // Cập nhật ngầm RAM để đồng bộ
            RADAR_DATA[ACTIVE_QC_COIL_ID]['prime_status'] = type;
            RADAR_DATA[ACTIVE_QC_COIL_ID]['quality_class'] = type === 'NON_PRIME' ? 'LOAI_1' : 'LOAI_2';
            RADAR_DATA[ACTIVE_QC_COIL_ID]['rework_status'] = 'FINAL';
            RADAR_DATA[ACTIVE_QC_COIL_ID]['qc_status'] = 'PASS';
            
            if (d.downgrade_reason) RADAR_DATA[ACTIVE_QC_COIL_ID]['downgrade_reason'] = d.downgrade_reason;
            
            // 🌟 LOGIC MỚI: Nhận trực tiếp cờ mapped_po do Backend tính toán (Hỗ trợ cả MTO chờ SO)
            if (d.mapped_po !== undefined) {
                RADAR_DATA[ACTIVE_QC_COIL_ID]['mapped_po'] = d.mapped_po;
            }
            
            renderActionCenter(ACTIVE_QC_COIL_ID);
            calculateSummary();
            renderInputList();
        } else {
            alert('❌ Lỗi: ' + d.msg);
        }
    }).catch(e => { hideLoading(); alert('Lỗi: ' + e); });
}

function openOrderRecommendationModal() {
    if (!ACTIVE_QC_COIL_ID) return alert("Vui lòng chọn cuộn trước!");

    showLoading();
    fetch('/api/recommend_order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ coil_id: ACTIVE_QC_COIL_ID })
    })
    .then(r => r.json())
    .then(d => {
        hideLoading();
        if (d.status === 'success') {
            const tbody = document.getElementById('tblRecommendBody');
            tbody.innerHTML = '';

            if (d.data.length === 0) {
                tbody.innerHTML = `<tr><td colspan="6" style="text-align:center; padding: 30px; color:#ef4444; font-weight:bold;">Không tìm thấy Order nào phù hợp tiêu chuẩn của cuộn này!</td></tr>`;
            } else {
                d.data.forEach(order => {
                    // Cờ has_room sẽ quyết định màu sắc (Ưu tiên xanh, đầy thì vàng/đỏ)
                    const roomBadge = order.has_room 
                        ? `<span style="background:#dcfce7; color:#166534; padding:3px 8px; border-radius:4px; font-size:0.8em; font-weight:bold;">✅ Còn Room</span>` 
                        : `<span style="background:#fef3c7; color:#92400e; padding:3px 8px; border-radius:4px; font-size:0.8em; font-weight:bold;">⚠️ Đã Đủ SL</span>`;

                    const tr = document.createElement('tr');
                    // Làm mờ nhẹ những đơn đã full
                    if(!order.has_room) tr.style.opacity = '0.75'; 

                    tr.innerHTML = `
                        <td style="font-weight: bold; color: #0f172a;">${order.order_id}</td>
                        <td style="color: #475569;">${order.so_mapping || '---'} <span style="font-size:0.7em; background:#e2e8f0; padding:2px 4px; border-radius:3px;">${order.prod_status}</span></td>
                        <td style="text-align: right; color: #475569;">${(order.req_min/1000).toFixed(1)} - ${(order.req_max/1000).toFixed(1)}</td>
                        <td style="text-align: right; font-family: monospace; font-size: 1.1em;">
                            <b style="color:${order.has_room ? '#16a34a' : '#ea580c'}">${(order.fulfilled_weight/1000).toFixed(1)}</b> / ${(order.total_weight/1000).toFixed(1)}
                        </td>
                        <td style="text-align: center;">${roomBadge}</td>
                        <td style="text-align: center;">
                            <button onclick="applyRecommendedOrder('${order.order_id}')" 
                                style="background:#3b82f6; color:white; border:none; padding:6px 12px; border-radius:4px; cursor:pointer; font-weight:bold;">
                                📥 Chọn Đơn
                            </button>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
            document.getElementById('mdlOrderRecommend').style.display = 'block';
        } else {
            alert('❌ Lỗi: ' + d.msg);
        }
    })
    .catch(e => { hideLoading(); alert('Lỗi hệ thống: ' + e); });
}

// Hàm thực thi khi bấm "Chọn Đơn"
function applyRecommendedOrder(newOrderId) {
    // ACTIVE_QC_COIL_ID là biến toàn cục bạn đang dùng trong file
    if(!confirm(`Xác nhận gắn cuộn ${ACTIVE_QC_COIL_ID} cho Order: ${newOrderId} ?`)) return;

    showLoading();
    fetch('/api/apply_order', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ 
            coil_id: ACTIVE_QC_COIL_ID, 
            order_id: newOrderId 
        })
    })
    .then(r => r.json())
    .then(d => {
        hideLoading();
        if(d.status === 'success') {
            // 1. Đóng Modal
            document.getElementById('mdlOrderRecommend').style.display = 'none';
            alert('✅ Đã ghi nhớ đơn hàng thành công!');
            RADAR_DATA[ACTIVE_QC_COIL_ID].suggested_order_map = newOrderId;
            RADAR_DATA[ACTIVE_QC_COIL_ID].qc_msg = '⏳ ĐANG CHỜ SAP ĐỔI SANG ĐƠN: ' + newOrderId;
            
            renderActionCenter(ACTIVE_QC_COIL_ID);
            calculateSummary();
            renderInputList();
        } else {
            alert('❌ Lỗi: ' + d.msg);
        }
    }).catch(e => {
        hideLoading();
        alert('Lỗi kết nối: ' + e);
    });
}
// 🌟 HÀM XỬ LÝ GỠ CỜ MAPPED PO
function removeMappedPo(coilId) {
    if (!confirm(`⚠️ Xác nhận gỡ cờ Mapped PO của cuộn ${coilId}?\nCuộn này sẽ được trả về dạng Tồn kho tự do (MTS).`)) return;

    showLoading();
    fetch('/api/remove_mapped_po', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ coil_id: coilId})
    })
    .then(r => r.json())
    .then(d => {
        hideLoading();
        if (d.status === 'success') {
            alert(d.msg);
            
            // 🌟 ĐỒNG BỘ RAM: Sửa Mapped PO về '0'
            if (RADAR_DATA[coilId]) {
                RADAR_DATA[coilId].mapped_po = '0';
            }
            
            // Vẽ lại bảng SUMMARY để xóa cái nhãn đó khỏi UI
            renderFullTable();
            
            // Nếu cuộn này đang được mở ở tab Nhập liệu, update luôn màn hình đó
            if (CURRENT_INPUT_COIL === coilId) {
                renderActionCenter(coilId);
            }
        } else {
            alert('❌ Lỗi: ' + d.msg);
        }
    })
    .catch(e => {
        hideLoading();
        alert('❌ Lỗi mạng: ' + e);
    });
}
function confirmUndoDowngrade(coilId) {
    if (!confirm(`⚠️ CẢNH BÁO: Bạn có chắc chắn muốn HỦY BỎ lệnh hạ cấp của cuộn ${coilId}?\nCuộn sẽ được mở khóa và trả về trạng thái PENDING để đánh giá lại từ đầu.`)) return;

    showLoading();
    fetch('/api/undo_downgrade', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ coil_id: coilId })
    })
    .then(r => r.json())
    .then(d => {
        hideLoading();
        if (d.status === 'success') {
            alert(d.msg);
            
            // 1. Đồng bộ RAM (xóa sạch các dữ liệu hạ cấp)
            if (RADAR_DATA[coilId]) {
                RADAR_DATA[coilId]['prime_status'] = null;
                RADAR_DATA[coilId]['quality_class'] = null;
                RADAR_DATA[coilId]['downgrade_reason'] = null;
                RADAR_DATA[coilId]['mapped_po'] = null;
                RADAR_DATA[coilId]['rework_status'] = 'NULL';
                RADAR_DATA[coilId]['qc_status'] = 'PENDING';
            }
            
            // 2. Kích hoạt render lại giao diện tại chỗ
            renderActionCenter(coilId);
            calculateSummary();
            renderInputList();
            renderFullTable();
        } else {
            alert('❌ Lỗi: ' + d.msg);
        }
    })
    .catch(e => {
        hideLoading();
        alert('❌ Lỗi kết nối máy chủ: ' + e);
    });
}
function triggerInlinePreview(val) {
    const orderId = val.trim().toUpperCase();
    const lblUiTdc = document.getElementById('lblUiTdc');
    
    // 1. NẾU XÓA TRẮNG (Về Null) -> Hủy ướm thử, trả Radar và TDC về mặc định
    if (!orderId) {
        RADAR_DATA[ACTIVE_QC_COIL_ID].tdc_limits = {};
        drawInteractiveRadars();
        
        // Trả lại TDC gốc của cuộn
        if (lblUiTdc) {
            const originalTdc = RADAR_DATA[ACTIVE_QC_COIL_ID].tdc_code || '---';
            lblUiTdc.innerText = originalTdc;
            lblUiTdc.style.color = '#0284c7'; // Trả về màu xanh nguyên bản
            lblUiTdc.style.fontStyle = 'normal';
        }
        return;
    }

    // 2. NẾU CÓ MÃ ORDER -> Gọi API lấy khung TDC
    showLoading();
    fetch('/api/get_preview_tdc', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ order_id: orderId })
    })
    .then(r => r.json())
    .then(d => {
        hideLoading();
        if (d.status === 'success') {
            // Ép khung viền mới vào biến RAM của cuộn hiện tại
            RADAR_DATA[ACTIVE_QC_COIL_ID].tdc_limits = d.tdc_limits;
            
            // Đổi màu nền ô Input thành xanh lá để báo hiệu đã load thành công
            const inputEl = document.getElementById('inlinePreviewOrder');
            if (inputEl) {
                inputEl.style.backgroundColor = '#dcfce7'; 
                inputEl.style.borderColor = '#16a34a';
                inputEl.style.color = '#15803d';
            }
            
            // [CẬP NHẬT MỚI]: Đổi hiển thị TDC Code sang của Order đang ướm thử
            if (lblUiTdc) {
                lblUiTdc.innerText = d.tdc_code;
                lblUiTdc.style.color = '#d97706'; // Đổi màu cam để biết đang Preview
                lblUiTdc.style.fontStyle = 'italic';
            }
            
            // Vẽ lại 4 biểu đồ Radar với dải xanh mới
            drawInteractiveRadars();
        } else {
            alert('❌ Lỗi: ' + d.msg);
            
            // Nếu KCS gõ sai mã Order -> Tự động reset ô input và Radar về Null
            const inputEl = document.getElementById('inlinePreviewOrder');
            if (inputEl) {
                inputEl.value = '';
                inputEl.style.backgroundColor = '#fffbeb';
                inputEl.style.borderColor = '#f59e0b';
                inputEl.style.color = '#d97706';
            }
            RADAR_DATA[ACTIVE_QC_COIL_ID].tdc_limits = {};
            drawInteractiveRadars();
            
            // Trả lại TDC gốc
            if (lblUiTdc) {
                lblUiTdc.innerText = RADAR_DATA[ACTIVE_QC_COIL_ID].tdc_code || '---';
                lblUiTdc.style.color = '#0284c7';
                lblUiTdc.style.fontStyle = 'normal';
            }
        }
    })
    .catch(e => {
        hideLoading();
        alert("Lỗi kết nối: " + e);
    });
}
function changeFullPage(d) { const max = Math.ceil(CURRENT_VIEW_LIST.length/50); if(FULL_PAGE+d>=1 && FULL_PAGE+d<=max) { FULL_PAGE+=d; renderFullTable(); } }
function upAjax(u,i){ const f=document.getElementById(i).files[0]; if(!f)return alert('Chọn file!'); const fd=new FormData(); fd.append('file',f); showLoading(); fetch(u,{method:'POST',body:fd}).then(r=>r.json()).then(d=>{alert(d.msg);location.reload()}).catch(e=>{hideLoading();alert('Lỗi:'+e)}); }
function deleteData(cat){ if(confirm('Xóa dữ liệu?')) { showLoading(); fetch('/delete_data_category',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({category:cat})}).then(r=>r.json()).then(d=>{alert(d.msg);location.reload()}).catch(e=>alert(e)); }}
function delCfg(e,n){e.stopPropagation();if(confirm('Xóa?'))fetch('/delete_config',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:n})}).then(()=>location.reload())}