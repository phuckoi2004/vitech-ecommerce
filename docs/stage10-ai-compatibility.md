# AI Compatibility Advisor trong chatbot VIETECH

Ngày bàn giao: 28/10/2026. Phạm vi: một laptop → một màn hình, hoặc kiểm tra chức năng xuất hình của một cổng laptop.

## 1. Chức năng đã hoàn thành

- Nhận câu hỏi kết nối, tương thích, cáp, USB-C video và yêu cầu độ phân giải/tần số quét trong cửa sổ AI Chat hiện có.
- Tìm sản phẩm đang hiển thị qua ProductService; giải quyết tên/model, “laptop thứ hai”, “màn hình đầu tiên”, sản phẩm vừa giới thiệu/vừa Smart Compare và câu hỏi nối tiếp “Nếu muốn xuất 4K 144Hz thì sao?”. Thứ tự laptop và màn hình được tra từ các danh sách riêng.
- Hỏi lại khi thiếu tên, trùng model, không tìm thấy, sản phẩm bị ẩn/xóa/ngừng bán hoặc chưa chọn SKU. Lựa chọn còn thiếu được lưu nội bộ để tiếp tục sau khi tải lại hội thoại.
- Giữ SKU đã tham chiếu kể cả khi hết hàng; không tự đổi sang phiên bản khác. Hỗ trợ thông số video riêng theo SKU. Các phiên bản chỉ khác màu (cùng giá, không có thông số video riêng) được tự chọn, không hỏi lại.
- Rule engine độc lập với Gemini, có bốn trạng thái; tách kết nối cơ bản, độ phân giải, tần số, chế độ toàn đường truyền, cáp/adapter và dữ liệu còn thiếu.
- Gemini chọn và sắp xếp các câu giải thích tiếng Việt đã được backend xác minh. Backend bỏ qua văn bản tự do, sản phẩm và kết luận do model tự đưa ra; không cho model thay đổi thông số/trạng thái.
- Khi provider timeout hoặc hết quota trong bước diễn giải, trả kết quả quy tắc và giải thích backend, giữ cơ chế cooldown hiện có. Cancellation và quyền sở hữu request vẫn được kiểm tra trước khi ghi tin.
- Hiển thị trong tin nhắn hiện tại: tên/ảnh liên kết chi tiết, trạng thái có biểu tượng và chữ, căn cứ kỹ thuật, điều kiện, thông số thiếu, giải thích và thời điểm snapshot. Render bằng React text, không chèn HTML từ AI.
- Khôi phục kết quả qua response, replay, GET trạng thái và GET lịch sử mà không tạo request Gemini mới. Chat thường, composer, chế độ phóng to và bảng Smart Compare dùng chung cửa sổ.

## 2. Các file của thay đổi này

### Tạo mới

| File | Vai trò |
|---|---|
| `backend/app/schemas/ai_compatibility.py` | Contract có version cho yêu cầu, thiết bị, tiêu chí và snapshot |
| `backend/app/services/compatibility_specs.py` | Đọc và chuẩn hóa JSONB kỹ thuật, chiều cổng, video, timing và cáp |
| `backend/app/services/compatibility.py` | Rule engine thuần, không gọi database hoặc Gemini |
| `backend/app/services/compatibility_intent.py` | Nhận câu hỏi, kế thừa yêu cầu và đọc độ phân giải/Hz/cổng |
| `backend/app/services/ai_compatibility.py` | Nối catalog, SKU, lịch sử, quy tắc và diễn giải an toàn |
| `backend/tests/test_compatibility.py` | Unit test độc lập cho quy tắc và chuẩn hóa |
| `backend/tests/test_ai_compatibility.py` | Test catalog/chat/API/lịch sử/provider và Smart Compare nối tiếp |
| `frontend/src/customer/components/AiCompatibility.jsx` | Component kết quả trong AI Chat |
| `frontend/src/customer/components/ai-compatibility.js` | Kiểm tra metadata, nhãn và dữ liệu text an toàn |
| `frontend/src/customer/components/AiCompatibility.test.jsx` | Test component và dữ liệu lỗi |
| `frontend/src/test/ai-compatibility.js` | Fixture giao diện, tách khỏi dữ liệu bán hàng |
| `docs/stage10-ai-compatibility.md` | Báo cáo và hướng dẫn này |

### Chỉnh sửa

| File | Thay đổi |
|---|---|
| `backend/app/services/ai_intent.py` | Thêm intent, slots và tham chiếu Compatibility |
| `backend/app/services/ai_tools.py` | Nhánh prepare/finish cho Compatibility trong công cụ hiện có |
| `backend/app/services/ai_chat.py` | Cấp kết quả quy tắc cho Gemini một vòng final, fallback và lưu snapshot |
| `backend/app/schemas/ai_chat.py` | Cho phép intent và mã câu giải thích an toàn trong `present_answer` |
| `backend/app/schemas/chat.py` | Chỉ công khai snapshot Compatibility hợp lệ; tiếp tục ẩn slots/lease |
| `backend/app/prompts/vietech_ai_protocol.py` | Hướng dẫn model chỉ giải thích kết quả backend |
| `frontend/src/customer/components/AiChatThread.jsx` | Render component trong tin AI và tránh lặp thẻ sản phẩm |
| `frontend/src/customer/components/AiChat.css` | CSS giới hạn trong `.ai-compatibility`, co theo khung chat |
| `frontend/src/customer/components/AiChat.test.jsx` | Test response và khôi phục đồng thời Compare/Compatibility |

Các file Smart Compare đã có trong workspace trước nhiệm vụ này, kể cả những file vẫn untracked trong Git. Không sửa `ai_comparison.py`, schema/component/helper/test so sánh hay `test_ai_grounded.py` trong nhiệm vụ Compatibility. Những thay đổi có trước trong các file tích hợp được giữ lại và đã đối chiếu với bản sao đầu nhiệm vụ.

Không thêm endpoint, trang Compatibility, chatbot, dependency, migration hoặc bảng database. Không sửa `.env` hay nghiệp vụ giỏ hàng/thanh toán/đơn hàng/kho/khuyến mãi; không commit, push hoặc deploy.

## 3. Kiến trúc và luồng xử lý

1. Frontend gửi qua endpoint AI hiện có với `ClientRequestId`.
2. Intent analyzer đọc câu hỏi và conversation slots. Yêu cầu so sánh hai laptop vẫn đi nhánh Compare; hỏi thông số để chọn mua vẫn đi nhánh hiện có.
3. `AiCompatibility.prepare()` xác định laptop/màn hình qua lịch sử và catalog công khai. Câu hỏi về điện thoại/sạc/hub/dock hoặc nhiều thiết bị được làm rõ phạm vi, không tái sử dụng cặp cũ.
4. ProductService đọc lại sản phẩm và SKU; normalizer chỉ đọc trường kỹ thuật của `Specifications`, không suy từ tên, GPU hoặc lời khách hàng.
5. `check_compatibility()` tính trạng thái, tiêu chí, căn cứ, điều kiện và phần còn thiếu. Kết quả có trước bước provider.
6. Service dùng đúng vòng gọi Gemini hiện có, chỉ cung cấp công cụ final `present_answer`. Model chọn tối đa sáu mã câu giải thích từ kết quả backend; không cần vòng tool mới.
7. `finish()` đọc lại visibility/SKU/thông số và chạy lại quy tắc sau provider I/O. Mã giải thích sai bị bỏ; các câu về điều kiện và phần chưa xác nhận luôn được giữ, kể cả khi model chỉ chọn câu kết nối tích cực.
8. Transaction ghi tin AI hiện có chứa `Metadata.Compatibility`, `ProductReferences` và slots nội bộ. Response chỉ công khai snapshot đã qua Pydantic.
9. `AiChatThread` render component. Replay/history hiển thị đúng snapshot cũ; câu hỏi mới kiểm tra dữ liệu hiện tại.

Snapshot `Version=1`, `RuleVersion=laptop-monitor-v1` chứa `CheckType`, danh sách `Products` với ProductId/SKU, `Request`, `Status`, `Criteria`, `Conditions`, `Missing`, `Limitations`, `Explanation`, nguồn giải thích và `SnapshotAt`. Metadata lỗi bị bỏ qua để không làm hỏng tải cả cuộc hội thoại.

“Đã xác minh” trong kết quả nghĩa là có trường kỹ thuật phù hợp trong catalog và đã qua quy tắc backend; không phải đã cắm thử thiết bị, tự tra tài liệu hãng hay kiểm chứng xuất xứ của dữ liệu catalog.

## 4. Quy tắc kỹ thuật

| Trạng thái | Căn cứ và phạm vi |
|---|---|
| `compatible` | Có video output → input phù hợp cho kết nối cơ bản, với điều kiện dùng cáp phù hợp; hoặc có đủ dữ liệu cho toàn bộ chế độ khách yêu cầu |
| `requires_adapter` | Có đường chuyển đổi đúng chiều được hỗ trợ trong quy tắc; phải dùng đúng loại cáp/bộ chuyển đã nêu, chưa khẳng định mọi SKU adapter đều đạt mọi chế độ |
| `incompatible` | Có danh sách cổng đầy đủ xác nhận thiếu chức năng video, giới hạn rõ ràng thấp hơn yêu cầu, hoặc không có cổng khớp trong yêu cầu chỉ kết nối trực tiếp |
| `unknown` | Thiếu dữ liệu chiều/chức năng cổng, đường chuyển đổi, timing, màu/DSC hoặc cáp; dữ liệu mâu thuẫn/chưa đọc đủ cũng không được dùng để khẳng định |

- HDMI output → HDMI input và DisplayPort output → DisplayPort input: xác nhận kết nối cơ bản, không suy ra 4K/Hz từ phiên bản cổng.
- USB-C → USB-C video: cần xác nhận DP Alt Mode ở cả hai đầu. Chữ USB-C đơn thuần hoặc Thunderbolt không tự chứng minh đường truyền phù hợp.
- USB-C có DP Alt Mode → DisplayPort/HDMI: nêu cáp chuyển đúng chiều. DisplayPort → HDMI: nêu bộ chuyển **chủ động**. Không tự đảo chiều HDMI → DisplayPort.
- Khi khách yêu cầu chế độ cụ thể, phải có timing theo từng cổng; Hz của panel không được dùng làm Hz đầu ra laptop hoặc timing đầu vào.
- Độ phân giải và tần số có tiêu chí riêng; kết luận chế độ toàn đường truyền chỉ dương tính khi cùng độ phân giải, Hz, định dạng màu, độ sâu màu, DSC ở hai đầu và cáp/bộ chuyển đã xác nhận đúng chế độ/chiều. Không ghép 4K60 với 1080p144 thành 4K144.
- Giới hạn tối đa chỉ tạo kết luận âm tính khi danh sách cổng đầy đủ và nhất quán. Không tìm thấy một chuẩn trong dữ liệu rời rạc không có nghĩa thiết bị không tương thích.
- Chỉ hỏi chức năng USB-C xuất hình có thể kiểm tra một laptop. Nếu hỏi thêm 4K/Hz mà chưa chọn màn hình, kết quả toàn đường truyền vẫn `unknown`, dù cổng laptop có video.
- `4K` được hiểu là UHD 3840×2160; `2K` và các tên K chưa hỗ trợ cần khách gửi kích thước cụ thể. “Chỉ cần kết nối cơ bản” bỏ mục tiêu độ phân giải/Hz trước đó.

Căn cứ chuẩn được đối chiếu với [DisplayPort FAQ](https://www.displayport.org/faq/), [DisplayPort over USB-C](https://www.displayport.org/displayport-over-usb-c/), [HDMI specifications](https://www.hdmi.org/spec/hdmi2) và [HDMI cables](https://www.hdmi.org/resource/cables). Các nguồn này phục vụ quy tắc chung; không lấy thông số sản phẩm bên ngoài để ghi vào catalog.

## 5. Đọc JSONB và xử lý thiếu dữ liệu

Normalizer đọc alias tiếng Việt/Anh và cấu trúc lồng nhau, bảo toàn input/output. “Cổng kết nối: HDMI 2.1, USB-C” được giữ làm thông tin nhưng không tự nâng thành cổng video đầu ra/đầu vào. Phủ định, “chỉ sạc”, “data only”, số cổng bằng 0, mô tả DP Alt Mode dưới USB-C và thông số mâu thuẫn được xử lý thận trọng. Bộ đọc có giới hạn kích thước; khi bị cắt hoặc có lỗi thì không coi danh sách là đầy đủ.

Định dạng cấu trúc sau được hỗ trợ ngay trong JSONB hiện có. Đây là **ví dụ fixture**, không phải thông số của sản phẩm thật và không được tự seed vào dữ liệu bán hàng:

```json
{
  "VideoOutputs": [{
    "Connector": "HDMI",
    "Version": "2.1",
    "Video": true,
    "Modes": [{
      "Width": 3840, "Height": 2160, "RefreshHz": 144,
      "ColorFormat": "RGB", "BitDepth": 8, "DSC": false
    }]
  }],
  "VideoOutputsComplete": true,
  "VideoCables": [{
    "From": "HDMI", "To": "HDMI", "Verified": true,
    "Evidence": "Bằng chứng kỹ thuật cho cáp cụ thể và chế độ tương ứng",
    "Modes": [{
      "Width": 3840, "Height": 2160, "RefreshHz": 144,
      "ColorFormat": "RGB", "BitDepth": 8, "DSC": false
    }]
  }]
}
```

Màn hình dùng `VideoInputs`/`VideoInputsComplete`; `VideoPorts` cần `Direction`. USB-C có thể ghi `DPAltMode` tường minh. `MaxResolution`/`MaxRefreshHz` là giới hạn của cổng đó. `VideoByVariant: {"<ProductVariantId>": {...}}` ghi đè theo đúng SKU. Chỉ đặt cờ Complete khi người quản lý dữ liệu đã xác nhận toàn bộ danh sách; cờ đơn lẻ không có danh sách hợp lệ bị bỏ qua. Các trường riêng tư và SKU khác không được dùng làm bằng chứng.

**Nhập qua trang admin.** Form sản phẩm chỉ lưu cặp tên/giá trị dạng chuỗi, nên không nhập được danh sách `VideoOutputs`/`VideoInputs`, timing đầy đủ hay `VideoCables`. Với admin, dùng tên thông số có chiều tín hiệu: laptop `Cổng xuất hình` (ví dụ `1x HDMI 2.1; 1x USB-C (DP Alt Mode)`), màn hình `Cổng nhận hình` (ví dụ `2x HDMI 2.1; 1x DisplayPort 1.4`). Chỉ ghi những gì tài liệu của hãng xác nhận. Cách này đủ để kết luận kết nối cơ bản và adapter; chế độ 4K/Hz đầy đủ vẫn `unknown` vì thiếu timing và cáp đã xác minh. Catalog mẫu chỉ có `Cổng giao tiếp`/`Cổng kết nối` không ghi chiều. Vì vậy, trước 29/10/2026, 875/875 cặp laptop × màn hình mẫu đều `unknown`. Từ 29/10/2026, Advisor suy chiều HDMI/DisplayPort theo loại thiết bị (mục 11). Tên có chiều như trên vẫn được ưu tiên, vì kết luận không phải ghi giới hạn "suy theo loại thiết bị".

Thiếu dữ liệu thì trả `unknown` và liệt kê những gì cần bổ sung; có đủ căn cứ kết nối cơ bản vẫn hiển thị riêng kết quả đó khi mục tiêu 4K144 chưa rõ. Không tạo giá trị mặc định, sản phẩm hay phụ kiện giả trong database.

## 6. Tích hợp Smart Compare

Giữ nguyên `Metadata.Comparison`, schema và component bảng. Các lượt Compatibility không trở thành một danh sách đề xuất mới, nên không làm lệch nghĩa “laptop thứ hai”. Sản phẩm/SKU trong bảng được dùng để tra lại thông số video cho lượt mới.

Test bao phủ chuỗi Compare hai laptop → giới thiệu màn hình → Compatibility laptop thứ hai → hỏi 4K144 → tải lại lịch sử/API. Bảng cũ được so sánh nguyên vẹn trước/sau; frontend kiểm tra cả hai component còn hiển thị sau remount và không gửi POST khi tải lịch sử. Luồng Compare đã xác định đủ SKU vẫn hoàn tất bằng backend, không thêm cuộc gọi Gemini.

## 7. Kiểm thử đã chạy

Fixture backend dùng SQLite cô lập và Gemini giả lập; không gọi Gemini thật hoặc database dùng chung trong nhiệm vụ này.

- Backend AI/chat/rule engine (sau rà soát mục 10): **149 test Compatibility** passed (`test_compatibility.py`, `test_ai_compatibility.py`). Hai cảnh báo deprecation từ Starlette/httpx và google-genai.
- Toàn bộ backend: 2128 passed, 138 skipped, 3 failed. Ba test fail nằm ngoài AI: `test_api_matrix` thiếu test thành công cho domain `return`, `test_internal_routes` có body 503 kèm `code`. `test_api_matrix` cũng fail trên HEAD sạch; các file liên quan không đổi so với HEAD.
- Frontend liên quan: **68 passed**, năm file `AiCompatibility`, `AiChat`, `AiComparison`, `AiChatText`, `CustomerChat`, chạy với một worker.
- Lint: exit 0, hai cảnh báo có trước ở `AdminTable.jsx` và `useAdminQuery.js`.
- Production build: thành công, 483 modules; còn cảnh báo chunk lớn của cấu hình hiện tại.
- Chrome headless: **8/8** tình huống ở desktop 1440px, mobile 390px/320px; chat thường/phóng to; đủ bốn trạng thái. Không tràn ngang, không có JavaScript exception, giữ bảng Compare, hai link chi tiết, không POST khi khôi phục history. Kịch bản dùng component thật với fixture cục bộ.
- Lượt chạy đồng thời cuối gặp thiếu bộ nhớ ở Vitest worker và Argon2 của test HTTP; đã dừng preview và chạy lại tuần tự. Không thay cấu hình mật khẩu, dependency hoặc bỏ test để che lỗi tài nguyên.

Backend test gồm: bốn trạng thái, USB-C chưa xác nhận, chuyển đổi đúng chiều, 4K/Hz tách biệt, màu/DSC/cáp, dữ liệu trống/phủ định/mâu thuẫn, SKU, sản phẩm thiếu/ẩn/xóa, tên/thứ tự, yêu cầu ngoài phạm vi, Compare nối tiếp, Gemini bịa nội dung/mã sai, timeout/quota, cancellation, replay và lịch sử qua API.

Lệnh chạy từ root, dùng môi trường Python/node_modules hiện có:

```powershell
Push-Location backend
$aiTestPaths = rg --files tests -g 'test_ai*.py' -g 'test_chat*.py' -g 'test_compatibility.py'
..\.venv\Scripts\python.exe -m pytest @aiTestPaths -q
Pop-Location
npm --prefix frontend test -- src/customer/components/AiCompatibility.test.jsx src/customer/components/AiChat.test.jsx src/customer/components/AiComparison.test.jsx src/customer/components/AiChatText.test.jsx src/customer/components/CustomerChat.test.jsx --maxWorkers=1
npm --prefix frontend run lint
npm --prefix frontend run build
```

Ảnh và phép đo kiểm tra cục bộ nằm trong `output/compatibility/`, là artifact ignored, không thuộc mã triển khai. Các số kiểm thử ở đây chỉ áp dụng phạm vi đã chạy, không phải xác nhận toàn bộ test của repository.

## 8. Giới hạn hiện tại

- Chưa kiểm tra chuỗi hub/dock, nhiều màn hình/MST, điện thoại/tablet/sạc, Power Delivery, USB dữ liệu, HDR/VRR, audio, chiều dài cáp hay benchmark thực tế.
- Chưa xác nhận tự động cáp/adapter thương mại theo model. `requires_adapter` nêu loại/chức năng/chiều có căn cứ; hiệu năng nâng cao cần dữ liệu timing cho đúng adapter/cáp.
- Không tính băng thông lý thuyết từ tên HDMI/DP, GPU hoặc Thunderbolt; dữ liệu đó chưa đủ để khẳng định đường truyền thực tế. Catalog chỉ có mô tả chung có thể cho nhiều kết quả `unknown`; đây là kết quả chủ đích.
- Chưa chạy smoke test với PostgreSQL dùng chung và Gemini thật trong nhiệm vụ này. Các test provider/API sử dụng model giả lập và database cô lập.
- Diễn giải Gemini có giới hạn: chọn/sắp xếp câu an toàn, không dùng văn bản diễn giải tự do. Khi không chọn được mã hợp lệ, dùng giải thích backend.

## 9. Kiểm tra thủ công trên website

Từ root, mở hai terminal với cấu hình local hiện có:

```powershell
.\.venv\Scripts\python.exe backend\scripts\run_dev.py
```

```powershell
npm --prefix frontend run dev
```

1. Đăng nhập tài khoản khách hàng trên local VIETECH, mở cửa sổ AI Chat.
2. Hỏi giới thiệu hai laptop hoặc so sánh hai model **có thật trong catalog local**. Xác nhận bảng Smart Compare hiện đúng.
3. Hỏi giới thiệu màn hình, chọn một tên/model cụ thể. Gửi “Laptop thứ hai vừa so sánh có kết nối được với màn hình <tên/model> không?”. Nếu chưa rõ SKU, trả lời lựa chọn mà chatbot hỏi.
4. Kiểm tra đúng hai thiết bị, link chi tiết, căn cứ, điều kiện cáp và trạng thái. Nếu catalog không ghi chiều/chức năng video, mong đợi `unknown`; không mong đợi cổng giả.
5. Hỏi “Nếu muốn xuất 4K 144Hz thì sao?”. Hai thiết bị phải giữ nguyên; kết nối cơ bản và chế độ nâng cao được trình bày riêng.
6. Hỏi “Chỉ cần kết nối cơ bản” rồi “Laptop này có hỗ trợ xuất hình qua USB-C không?”. Lượt đầu bỏ mục tiêu 4K144; lượt sau chỉ kiểm tra cổng laptop, không dùng HDMI thay cho USB-C.
7. Thử tên không tồn tại, “laptop của tôi”, hoặc tên nhiều model trùng: chatbot phải hỏi bổ sung. Hỏi điện thoại/sạc/hub: không nhận lại kết quả cặp cũ.
8. Tải lại trang/mở lịch sử, thu nhỏ/phóng to và thử chiều rộng 320/390px. Bảng Compare và thẻ Compatibility cũ vẫn hiện; snapshot có thời điểm tư vấn, không tự cập nhật kết quả cũ.
9. Hỏi chat thông thường và so sánh hai laptop tiếp để kiểm tra luồng sẵn có.

Các tình huống thiếu cổng, adapter, chế độ đầy đủ, provider timeout/quota và sản phẩm ẩn/xóa có fixture test riêng. Không cần sửa sản phẩm hoặc quota thật để tạo các tình huống này.

## 10. Rà soát và sửa lỗi (28/10/2026)

Các lỗi dưới đây đã được tái hiện bằng script trên code trước khi sửa, sau đó sửa và thêm regression test.

**Suy luận kỹ thuật** (`compatibility_specs.py`, `compatibility.py`)

- Cụm "DP Alt Mode"/"DP over USB-C" ở mệnh đề tách rời ("Cổng xuất hình: USB-C, hỗ trợ DP Alt Mode") tạo ra một cổng DisplayPort vật lý giả. Kết quả là kết luận `compatible` bằng "Cáp DisplayPort", trong khi laptop thật sự cần cáp USB-C → DP. Ngoài ra 17/35 laptop mẫu bị đọc thêm cổng DP từ "USB-C (…, DisplayPort 1.2)". Sau khi sửa, chỉ còn Acer Aspire 7, máy có Mini DisplayPort thật. "Type-C" không kèm chữ USB nay được nhận là USB-C.
- "no DP Alt Mode"/"không hỗ trợ DP Alt Mode" bị đọc thành **có** Alt Mode. Nay đọc là không có. Dạng "DP Alt Mode: Không" cũng được xử lý.
- Kết luận âm tính theo giới hạn Hz/độ phân giải bỏ qua cổng USB-C có video nhưng chưa rõ giao thức. Nay danh sách cổng phải rõ ràng thì mới được kết luận `incompatible`.
- Thunderbolt có cấu trúc ("Thunderbolt 4") từng bị loại như mục không đọc được. Nay đọc được, nhưng chỉ dùng làm nguồn DP khi có DP Alt Mode tường minh. Danh sách chỉ có Thunderbolt không còn bị dùng để kết luận "không có USB-C".
- "DC-in 65W", "đầu vào nguồn" không còn biến cổng USB-C của laptop thành đầu vào video. `Direction` không phân biệt hoa thường. "chế độ Alt" được hiểu là DP Alt Mode.

**Ý định và ngữ cảnh** (`compatibility_intent.py`, `ai_compatibility.py`, `ai_intent.py`)

- Trước đây mọi câu có "tương thích" hoặc "kết nối" + "laptop" đều bị đưa vào Compatibility và chatbot hỏi tên màn hình. Ví dụ: Wi-Fi, Bluetooth, Windows 11, RAM, "cổng kết nối gì", "màn hình đạt 144Hz không". Nay chỉ câu về đường truyền hình ảnh mới vào Compatibility. Điện thoại/sạc/hub vẫn nhận câu trả lời về phạm vi hỗ trợ.
- Sau một lượt kiểm tra, hoặc khi chatbot đang chờ khách bổ sung thiết bị, các câu như "Còn màn hình nào rẻ hơn?" hay "Laptop nào dưới 20 triệu?" bị giữ lại trong Compatibility. Nay câu có ngân sách, nhu cầu, gợi ý, so sánh, khuyến mãi, chính sách hoặc giá/thông số được chuyển về luồng tư vấn sẵn có.
- Câu nối tiếp "Còn laptop thứ nhất thì sao?" từng không được nhận. Nay nó giữ màn hình đang xét và yêu cầu 4K/Hz trước đó. "Máy thứ hai" đứng cạnh tên màn hình nay lấy đúng từ danh sách vừa so sánh, không bị hiểu là màn hình thứ hai.
- "qua USB-C/HDMI/DP" từng bị bỏ qua nếu câu không có chữ "xuất hình", và tên model bị dính "qua …". Câu hỏi mới đầy đủ không còn âm thầm kế thừa cổng, chế độ hoặc lựa chọn "chỉ kết nối trực tiếp" của lượt trước.
- "Laptop nào kết nối được màn hình X?" nay được trả lời rằng hệ thống chỉ kiểm tra từng cặp, không tìm catalog với từ khóa "nao".

**Lưu trữ và hiển thị**

- Khi Gemini lỗi và thông số có nhiều cảnh báo, ghi chú dự phòng làm `Limitations` vượt 12 mục. Snapshot không qua schema nên thẻ kết quả biến mất khỏi response và lịch sử. Nay danh sách được giới hạn và snapshot được kiểm tra schema trước khi lưu.
- Nội dung tin nhắn nêu riêng kết nối cơ bản và chế độ yêu cầu khi hai kết quả khác nhau. Thẻ kết quả hiển thị cổng khách đã chọn và lựa chọn "chỉ kết nối trực tiếp". Tiêu đề giải thích là "GIẢI THÍCH CỦA AI" khi Gemini chọn câu, và "GIẢI THÍCH TỪ QUY TẮC KIỂM TRA" khi dùng phần dự phòng của backend.

**Bổ sung sau rà soát**

- Trong thời gian chờ sau khi Gemini hết quota, câu hỏi Compatibility vẫn được trả lời bằng kết quả quy tắc và giải thích backend (`AnalysisStatus=fallback`), không gọi Gemini. Câu hỏi lại cũng không cần Gemini. Mọi câu hỏi khác vẫn bị từ chối trước khi lưu như cũ. Sau bước phân tích, `ask()` kiểm tra lại cooldown.
- Câu hỏi lại trích tên đúng như khách gõ ("Samsung Odyssey Đen"), không còn dạng không dấu.
- Câu chào hỏi/cảm ơn khi chatbot đang chờ tên thiết bị không còn bị hiểu là tên màn hình.

**Còn giới hạn:** kiểm tra chỉ laptop (không chọn màn hình) chưa dùng giới hạn tối đa của cổng laptop để kết luận âm tính. "Giá treo màn hình" thuộc danh mục màn hình nên được coi là màn hình (kết quả `unknown`).

## 11. Sửa sau nghiệm thu (29/10/2026)

Nguồn: `output/final-data-acceptance/FINAL_ACCEPTANCE_REPORT.md` (CA02–CA08, CA10). Regression test: `backend/tests/test_ai_acceptance_fixes.py`.

- **CA04 (nghiêm trọng).** "MacBook Air M5 15 inch xuất 4K 60Hz ra màn hình Dell U2424H được không?" bị đưa vào luồng `product`; Gemini tự viết "hoàn toàn có thể xuất tín hiệu…". Có hai lớp sửa:
  - `explicit_compatibility` nhận "xuất 4K/60Hz/tín hiệu … ra màn hình".
  - Ở mọi luồng khác, `check_message` (`ai_grounding.py`) từ chối câu kết luận tương thích, kết nối, xuất hình hoặc cần adapter không có trong thông số catalog. Câu hỏi của khách không được tính là căn cứ. Khi đó backend hiển thị văn bản có căn cứ của mình.
- **CA02, CA05–CA07.** Thêm các cách hỏi:
  - "nối/cắm/chạy/chơi … với/trên/vào màn hình <model>";
  - "cần adapter gì để nối laptop … với màn hình …".
  Câu chỉ nói về màn hình của chính laptop ("chơi game trên màn hình 144Hz", "màn hình 2.8K") vẫn đi luồng tư vấn. Tên model không còn dính "nối/cổng/chạy/chơi/ra …" hoặc "1920x1080". "nối/dùng cổng USB-C" được đọc là cổng của laptop.
- **CA03.** Tên lưu với gạch nối không ngắt U+2011 ("HP 14‑EM0023AU") không tìm được bằng "-". `fold()` và câu SQL tương ứng (`search_text.py`) nay đổi các dấu gạch U+2010–U+2014 và U+2212 thành "-". Thay đổi này áp dụng cho cả tìm kiếm của khách.
- **CA08.** Khi các phiên bản chỉ khác màu, chatbot hỏi chọn màu. Nay tự chọn phiên bản theo `colour_only_default`: ưu tiên còn hàng, sau đó theo tên. Điều kiện: cùng giá, cùng tên sau khi bỏ màu, không có `VideoByVariant` riêng.
- **Tên khớp nhiều sản phẩm.** `closest_products`: "MacBook Air M5 13 inch 16GB 512GB" chọn bản tiêu chuẩn, không chọn bản "Sạc 70W". Hai cấu hình khác nhau vẫn được hỏi lại.
- **CA10.** Sau khi Smart Compare hoàn tất (xem `stage10-ai-smart-compare.md`), "Máy thứ hai có xuất hình ra màn hình …" lấy đúng máy thứ hai trong bảng.

**Chiều tín hiệu suy theo loại thiết bị** (quyết định của chủ dự án, 29/10/2026)

Trước đây catalog chỉ ghi tên cổng ("2 x HDMI; 1 x DisplayPort"), nên 0/875 cặp thật có kết luận.

`AiCompatibility.build` nay truyền `device_kind` cho `normalize_video_specs`:
- Cổng HDMI/DisplayPort không ghi chiều trong danh sách cổng: laptop coi là xuất hình, màn hình coi là nhận hình.
- USB-C/Thunderbolt chỉ được tính khi chính cổng đó ghi DisplayPort hoặc DP Alt Mode.
- Cổng ghi "out"/"in" giữ nguyên chiều đã ghi. USB-C ghi trơn vẫn là chưa xác nhận.
- Cổng suy ra mang cờ `inferred`. Kết luận dùng câu "Laptop có cổng … và màn hình có cổng nhận phù hợp trong danh sách cổng…" (không viết "đã xác minh") và thêm giới hạn `INFERRED_NOTE`.
- Snapshot có trường `Basis`:
  - `stated` (mặc định, đủ cho snapshot cũ): chiều cổng do thông số ghi rõ.
  - `device_type`: có giới hạn `INFERRED_NOTE`.

  Với `device_type`, câu mở đầu trong chat ghi "Có thể kết nối cơ bản (chiều xuất/nhận hình suy theo loại thiết bị)" hoặc "Cần cáp hoặc bộ chuyển đổi phù hợp (…)". Nhãn trên thẻ kết quả ghi "Có thể kết nối (suy theo loại thiết bị)", không ghi "Có căn cứ xác nhận". Lần chạy Gemini thứ 3 (CA01, CA10) cho thấy nhãn cũ đọc như hãng đã xác nhận chiều cổng. Đây không phải thay đổi database: `Basis` nằm trong JSON metadata của tin nhắn.
- Đường kết nối có chiều ghi rõ được ưu tiên.
- Chế độ 4K/Hz vẫn cần timing ở cả hai đầu.
- Các nơi gọi không truyền `device_kind` (test quy tắc, script cũ) giữ cách đọc cũ.

**Đợt dữ liệu cổng 2** (29/10/2026, `output/catalog-port-data-2/PORT_DATA_REVIEW.md`)

Bộ đọc nay đọc chế độ hãng công bố trong văn bản của từng cổng: "1 x HDMI 1.4 (xuất hình tối đa 1920x1080 @ 60Hz)", "4K@60Hz", "8K/60Hz", "FHD@60 Hz".
- Không đọc "2K", và không đọc tần số không kèm độ phân giải.
- Chế độ đọc từ văn bản không có định dạng màu, độ sâu màu hay DSC. Vì vậy chế độ tín hiệu đầy đủ (R3/R4) vẫn cần dữ liệu có cấu trúc và cáp đã xác minh.
- Cổng USB-C/Thunderbolt ghi rõ chiều xuất/nhận hình và tự nêu DisplayPort được tính là DP Alt Mode, như với cổng suy theo loại thiết bị.

27 giá trị có nguồn hãng đã được Phase B `--apply` ghi vào Supabase lúc 20:05:00 +07:00 ngày 29/10/2026 theo yêu cầu chủ dự án. SELECT lúc 20:05:12 xác nhận khớp toàn bộ danh sách, receipt `committed_verified`; không đổi bảng/cột/khóa thuộc tính, giá, tồn kho, SKU hoặc media. UpdatedAt của 27 sản phẩm được trigger sẵn có cập nhật. Backup và bằng chứng tại `output/catalog-port-data-2/phase-b/20261029-170557-19293110/`; xem `APPLIED.md` và `independent-verification.json`.

**Quy tắc R4b: chế độ trong mức tối đa hãng công bố** (chủ dự án đồng ý, 29/10/2026)

Hãng thường chỉ công bố chế độ **tối đa** của từng cổng, không kèm định dạng màu, độ sâu màu hay DSC. Vì vậy R4 (chế độ đầy đủ và cáp đã xác minh) gần như không bao giờ có kết luận. R4b áp dụng cho chế độ đọc từ văn bản (`VideoPort.limits`), trong `compatibility._published`.

| Trường hợp | Kết luận |
|---|---|
| Hai đầu của **cùng một** đường kết nối có mức tối đa bao trùm chế độ khách hỏi: cùng tỉ lệ khung hình, độ phân giải và tần số không cao hơn | `compatible`, hoặc `requires_adapter` nếu đường đó cần cáp chuyển |
| Trên **mọi** đường kết nối, một đầu có mức tối đa thấp hơn chế độ khách hỏi: độ phân giải nhỏ hơn, hoặc tần số thấp hơn ở đúng độ phân giải đó | `incompatible` |
| Còn lại, ví dụ độ phân giải thấp hơn nhưng tần số cao hơn mức đã công bố, hoặc có một đường chưa có số liệu | `unknown` |

Kết luận `compatible`/`requires_adapter` theo R4b có:
- điều kiện "Cáp hoặc bộ chuyển đổi phải hỗ trợ W×H @ X Hz.";
- giới hạn `PUBLISHED_NOTE` (định dạng màu, độ sâu màu và DSC chưa được hãng xác nhận);
- snapshot `ModeBasis = published_max`.

Nếu chế độ chỉ đạt qua một đường cần cáp chuyển, tiêu chí "chế độ tín hiệu" cũng là `requires_adapter`, giống kết luận tổng (CA13). Câu mở đầu ghi "Chạy được theo mức tối đa hãng công bố, cần cáp đạt chuẩn". Câu hỏi kiểu "<laptop> chạy/dùng màn hình <tên mẫu> ở …" cũng được nhận là câu hỏi tương thích (`_RUNS_MONITOR`). Nhãn trên thẻ ghi "Chạy được theo mức tối đa hãng công bố". Khi khách chỉ hỏi tần số ("144Hz được không"), chế độ được kiểm tra ở độ phân giải hãng công bố cho cổng của màn hình. Dữ liệu có cấu trúc (`VideoOutputs`/`VideoInputs`) vẫn theo R4 như cũ.

Kiểm tra ngoại tuyến bằng quy tắc hiện hành trên bản SELECT sau khi áp dụng đợt dữ liệu 2, gồm 875 cặp:

| Câu hỏi | Có kết luận | Gồm |
|---|---|---|
| 1080p60 | 120 | 60 chạy trực tiếp, 60 cần cáp chuyển |
| 1080p120 | 63 | 24 chạy được, 39 không đạt |
| 1440p144 | 88 | 5 chạy được, 83 không đạt |
| 4K60 | 117 | 117 không đạt; chưa màn hình 4K nào có số liệu từng cổng |

Kết quả trên catalog sau khi áp dụng đợt dữ liệu 2:
- 782/875 cặp có kết luận kết nối cơ bản: 593 kết nối trực tiếp, 189 cần cáp chuyển.
- 93 cặp còn lại: 70 cặp của 2 "giá treo màn hình" và 23 cặp của Acer Swift Air 14. MacBook Air M2 đã có bổ sung DisplayPort qua USB-C theo danh sách đợt 2; không chạy lại đề xuất riêng cũ tại `output/catalog-port-data/`.

**Đợt dữ liệu cổng 3 — LG 4K và Acer Swift Air 14** (29/10/2026)

Đã commit hai giá trị Specifications vào Supabase lúc **20:49:26 +07:00**, SELECT xác nhận lúc **20:49:34**. Không thêm bảng, cột hay khóa thuộc tính; giá, tồn kho, SKU và media giữ nguyên. Chỉ UpdatedAt của hai sản phẩm được trigger sẵn có cập nhật.

- **LG 27G850A-B:** 2 HDMI 2.1 và 1 DisplayPort 2.1 nhận tối đa 4K@240Hz hoặc FHD@480Hz, theo bảng tín hiệu vào LG và đối chiếu đúng model 27G850A-B.
- **Acer Swift Air 14 SFA14-I31-55NR:** hướng dẫn chính hãng SFA14-I31, trang 14/64, xác nhận DisplayPort qua USB-C. Gộp DC-in vào chức năng của 2 USB-C, không mô tả thành cổng thứ ba. Không tự gán 4K60 do hãng không ghi Hz.
- **Hai giá treo EDRA:** VESA và tải 2–10 kg đã khớp nguồn hãng; không thêm cổng video. Dải kích cỡ EMA7304 có nguồn mâu thuẫn nên giữ nguyên và đánh dấu cần xem lại.

Kiểm tra trên actual readback bằng bộ đọc hiện hành: **114 test đạt**, **12.250** lượt đối chiếu trước/sau với 7 loại yêu cầu. Kết nối cơ bản có kết luận cho **805/805 cặp với màn hình thật** (595 trực tiếp, 210 cần cáp chuyển); 70 lượt unknown trong ma trận theo danh mục cũ thuộc 2 giá treo cơ khí. Swift Air 14 có kết luận cơ bản với cả 23 màn hình thật.

| Yêu cầu | Trực tiếp | Cần cáp chuyển | Không đạt | Chưa đủ dữ liệu |
|---|---:|---:|---:|---:|
| 4K60 | 8 | 10 | 120 | 737 |
| 4K144 | 0 | 5 | 200 | 670 |
| 4K240 | 0 | 5 | 200 | 670 |

Mọi kết luận theo R4b tiếp tục giữ điều kiện cáp và giới hạn màu/độ sâu màu/DSC. Không có thay đổi hoặc triển khai lại code server trong đợt ghi dữ liệu. Evidence mới: `backend/data/catalog-port-evidence-round3-2026-10-29.json`; báo cáo, nguồn, backup và receipt tại `output/catalog-port-data-3/PORT_DATA_REVIEW.md` và `output/catalog-port-data-3/phase-b/20261029-204821-b3300c19/`.
