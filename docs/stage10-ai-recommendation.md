# Bước 10.6 — Xếp hạng gợi ý sản phẩm

Hoàn thành ngày 22/10/2026 theo mục 10 “Recommendation engine” của tài liệu `VieTech_GiaiDoan10_Google Gemini_TaiLai.docx`. Khách vẫn chỉ gửi câu hỏi; không thêm nút, API, bảng hay migration.

> **Cập nhật cùng ngày — [nâng cấp tư vấn theo catalog](stage10-ai-advisor-upgrade.md).** Công thức hiện hành không dùng H: Score = (0,40N + 0,25B + 0,20T) / 0,85, chuẩn hóa theo tiêu chí đang áp dụng. Thay đổi so với nội dung bên dưới:
> - N dùng điểm liên tục thay vì đạt/không đạt, và có hồ sơ cấu hình cân bằng khi khách không nêu nhu cầu.
> - Tiêu chí không ứng viên nào có dữ liệu bị loại; đọc được pin “WHrs/watt‑giờ” và chip trong tên máy.
> - Tối đa 60 ứng viên (30/trang).
> - Không lặp sản phẩm đã giới thiệu.
>
> Phần dưới đây mô tả phiên bản 10.6 để đối chiếu.

## Hai tầng: lọc cứng trước, xếp hạng sau

1. **Lọc cứng** (giữ nguyên bước 10.3): sản phẩm đang bán, có biến thể còn hàng, giá thực bán không vượt ngân sách, đúng danh mục, đúng hãng bắt buộc (“chỉ ASUS”, “laptop Dell”), loại hãng bị loại trừ (“không mua ASUS”). Không có sản phẩm đạt thì trả “chưa chọn được sản phẩm phù hợp”, không xếp hạng cố.
2. **Xếp hạng mềm** (mới): lấy tối đa **20 ứng viên** đã qua lọc cứng, tính điểm, sắp xếp và đưa **tối đa 5** cho model; câu trả lời vẫn hiển thị tối đa 3 thẻ.

Thay đổi về lọc: cụm nhu cầu như “pin trâu”, “chơi game”, “lập trình” trước đây có thể khớp tên nhóm con của VieTech (ví dụ “Điện thoại pin trâu”) và bị dùng làm bộ lọc cứng. Theo tài liệu, các cụm này là tiêu chí mềm, nên backend lọc theo danh mục cha (“Điện thoại”) và chấm điểm nhu cầu. Ví dụ trên catalog thật: “Điện thoại pin trâu chụp ảnh đẹp khoảng 15 triệu” tăng từ 4 lên 17 ứng viên.

## Công thức

```
Score = Σ(wᵢ × sᵢ) / Σ(wᵢ),  i ∈ tiêu chí đang hoạt động
w: N = 0,40   B = 0,25   T = 0,20   H = 0,15
```

| Tiêu chí | Hoạt động khi | Điểm (0–1) |
|---|---|---|
| **N** — Nhu cầu | Câu hỏi có cụm nhu cầu (bảng dưới) | Tỷ lệ có trọng số các tiêu chí thông số **đã đạt**; thiếu dữ liệu tính là chưa đạt |
| **B** — Ngân sách | Có ngân sách tối đa (từ câu hỏi hoặc lượt trước) | `0,70 + 0,30 × (Ngân sách − Giá) / Ngân sách`, chặn 0–1; không có ý “càng đắt càng tốt” |
| **T** — Hãng ưu tiên mềm | Khách nêu hãng nhưng không bắt buộc (“ưu tiên ASUS”, “ASUS hoặc Lenovo”) | 1 nếu đúng hãng, 0 nếu khác |
| **H** — Lịch sử | Khách có sản phẩm yêu thích hoặc đơn đã giao (bước 10.5) | 0,5 × cùng hãng + 0,5 × cùng danh mục, lấy cao nhất; **sản phẩm khách đã mua = 0** để không gợi ý mua lại |

Tiêu chí không hoạt động bị loại và trọng số được chuẩn hóa lại. Ví dụ chỉ có N và B: trọng số hiệu dụng là 0,40/0,65 và 0,25/0,65. Không tiêu chí nào hoạt động (ví dụ “Tư vấn laptop”, không ngân sách, chưa có lịch sử) thì giữ thứ tự catalog. Đồng điểm: ưu tiên sản phẩm có đủ dữ liệu thông số hơn, sau đó theo `ProductId` để kết quả ổn định.

## Tiêu chí nhu cầu N

Ngưỡng là giả thuyết thiết kế để kiểm nghiệm ở bước 10.7, không phải công thức tối ưu. Mỗi nhu cầu có thêm tiêu chí “thuộc nhóm VieTech” (trọng số 0,2) khi sản phẩm nằm trong nhóm con tương ứng, ví dụ “Laptop lập trình”.

| Nhu cầu (cụm nhận diện) | Loại hàng | Tiêu chí (trọng số) |
|---|---|---|
| Lập trình (“lập trình”, “code”, “developer”) | Laptop | RAM ≥ 16 GB (0,35); ổ cứng ≥ 512 GB, không phải HDD (0,25); CPU nhóm Core i5/Ultra 5/Ryzen 5/Apple M trở lên (0,25); khe RAM nâng cấp được (0,15) |
| Chơi game (“chơi game”, “gaming”, “game”) | Laptop | GPU rời RTX/GTX/Radeon RX/Arc (0,45); RAM ≥ 16 GB (0,30); màn hình ≥ 120 Hz (0,25) |
| | Điện thoại / Máy tính bảng | RAM ≥ 8 GB; màn hình ≥ 120 Hz (máy tính bảng ≥ 90 Hz) |
| Học tập/văn phòng (“học tập”, “sinh viên”, “văn phòng”, “làm việc”) | Laptop | RAM ≥ 8 GB (0,35); ổ cứng ≥ 256 GB (0,30); nặng ≤ 1,6 kg (0,35) |
| | Máy tính bảng | RAM ≥ 4 GB; bộ nhớ ≥ 128 GB |
| Pin (“pin trâu”, “pin tốt”, “pin lâu”) | Điện thoại | Pin ≥ 5.000 mAh (0,7); sạc ≥ 33 W (0,3) |
| | Máy tính bảng / Laptop | Pin ≥ 7.000 mAh / ≥ 50 Wh |
| Chụp ảnh (“chụp ảnh”, “camera”, “quay phim”) | Điện thoại | Có chống rung quang học (0,6); có ống kính tele/zoom quang (0,4) |
| Mỏng nhẹ (“mỏng nhẹ”, “nhỏ gọn”, “nhẹ”) | Laptop / Điện thoại | Nặng ≤ 1,5 kg / ≤ 190 g |

Quy tắc dữ liệu:

- Đọc đúng các khóa đang có trong `Specifications` của catalog (ví dụ `Dung lượng RAM`, `Ổ cứng`, `Loại CPU`, `Loại card đồ họa`, `Pin`, `Camera sau`), không phân biệt hoa thường/dấu; số như “5.000 mAh”, “60,9 Wh”, “1TB” được chuẩn hóa.
- Thiếu khóa → “chưa có dữ liệu …”, tính là chưa đạt. Văn bản không nhắc tính năng (ví dụ camera không ghi chống rung) → “chưa xác nhận …”, cũng tính là chưa đạt.
- Không suy ra chất lượng camera từ số MP; dung lượng pin chỉ là tín hiệu, câu trả lời ghi rõ thời lượng thực tế tùy cách dùng.
- Ổ cứng chỉ ghi “512GB” được tính theo dung lượng; chỉ khi ghi HDD mới bị coi là không đạt. Trên catalog hiện tại chỉ 2/35 laptop ghi tần số quét, nên tiêu chí 120 Hz thường là “chưa có dữ liệu”.
- Loại hàng (laptop/điện thoại/máy tính bảng) lấy từ danh mục gốc. Nhu cầu không có tiêu chí cho loại hàng đó (ví dụ “pin trâu” với chuột) chỉ còn tiêu chí nhóm VieTech.

## Dữ liệu model nhận và câu trả lời

Mỗi sản phẩm trong kết quả `search_products` có thêm `Ranking`: `Rank`, `Score`, `Parts` (N/B/T/H đang hoạt động), `Matched` (tối đa 4 bằng chứng từ thông số) và `Gaps` (tối đa 3 tiêu chí chưa đạt/chưa có dữ liệu). Kết quả có `Ranked`, `Eligible` và `CandidateLimit`. Prompt yêu cầu model chọn theo Rank và không tự chấm lại.

Khi `intent=recommend`, backend đọc lại giá/tồn hiện tại, tính lại điểm và **sắp thẻ theo điểm**, không theo thứ tự model liệt kê. Mỗi sản phẩm có thêm dòng do backend dựng từ dữ liệu đã xác nhận, ví dụ:

```
1. Laptop MSI Modern 15 F1MG-1225VN
Phiên bản: …; giá: 19.791.000 đ; còn hàng.
Phù hợp: RAM 16 GB; ổ cứng 512 GB; CPU Intel Core 5 120U; RAM nâng cấp được; trong ngân sách 20.000.000 đ.
```

Có thể kèm “đúng hãng bạn ưu tiên”, “cùng hãng/nhóm với sản phẩm bạn đã yêu thích hoặc đã mua”, và dòng “Lưu ý: …” cho tiêu chí chưa đạt hoặc “bạn đã mua sản phẩm này trước đây”. Model không tự viết số liệu.

Khách yêu cầu thứ tự cụ thể (“rẻ nhất”, “giá thấp nhất”, “giá tăng/giảm dần”, “đắt nhất”, “mới nhất”) thì giữ thứ tự đó: không xếp hạng khi tìm và không sắp lại thẻ; vẫn có dòng “Phù hợp/Lưu ý”.

Điểm được lưu trong metadata nội bộ của tin yêu cầu: `AiRanking = {Ordered, Needs, SoftBrands, History, Products: [{ProductId, Score, Parts}]}`, phục vụ đánh giá 10.7. Customer không nhận trường này, thẻ sản phẩm không chứa điểm. Không có migration (dùng cột `Messages.Metadata` sẵn có).

## So sánh có/không xếp hạng

`AI_RANKING_ENABLED` trong `backend/.env` (mặc định `true`). Đặt `false` rồi khởi động lại backend để chạy baseline: cùng bộ lọc cứng, kết quả theo thứ tự catalog (giá tăng dần), không có `Ranking`, không sắp lại thẻ, không lưu `AiRanking`. Dùng để đo tiêu chí nghiệm thu “ranking không kém baseline” ở 10.7.

Kiểm tra nhanh trên catalog thật (chỉ đọc, không gọi Gemini, ngày 22/10/2026):

| Câu hỏi | Ứng viên đạt lọc cứng | Hạng 1 khi xếp hạng | Hạng 1 baseline |
|---|---|---|---|
| Laptop học lập trình dưới 20 triệu | 4 | MSI Modern 15 F1MG (16 GB RAM, Core 5, 512 GB; 0,78) | MacBook Neo 13 A18 Pro 8 GB/256 GB (rẻ nhất) |
| Laptop chơi game dưới 30 triệu | 20 (chạm giới hạn) | ASUS TUF Gaming F16, RTX 3050 (0,79) | MacBook Neo 13 (không GPU rời) |
| Điện thoại pin trâu chụp ảnh đẹp khoảng 15 triệu | 17 | OPPO Reno16 F (0,71) | Itel P55 Plus (rẻ nhất) |

Đây là kiểm tra hoạt động, không phải kết quả đánh giá chất lượng; đánh giá theo bộ câu hỏi thuộc 10.7.

## Hiệu năng

Chấm điểm cần thông số của mọi ứng viên. `ProductService.get_product_details(ids)` tải sản phẩm, biến thể, ảnh trong một lần truy vấn và đọc khuyến mãi tự động một lần, cho kết quả giống hệt `get_product_detail` từng sản phẩm (có test). Đo trên database phát triển: một lần tìm có xếp hạng giảm từ khoảng 8,5 giây (20 lần tải riêng) xuống khoảng 0,9 giây; tìm không xếp hạng từ 2,4 xuống 0,7 giây.

## Tệp chính

- `backend/app/services/recommendation.py`: tiêu chí, ngưỡng, công thức, chuẩn hóa trọng số, quy tắc đồng điểm. Không truy cập database.
- `backend/app/services/ai_tools.py`: hãng ưu tiên mềm, nới nhóm con mang tên nhu cầu, chấm điểm trong `search_products`, sắp thẻ và dòng lý do trong `finish`.
- `backend/app/services/catalog.py`, `backend/app/repositories/catalog.py`: tải chi tiết theo lô.
- `backend/app/repositories/ai_personalization.py`: danh sách sản phẩm đã mua cho H (chỉ dùng nội bộ, không gửi model).
- `backend/app/core/ai_config.py`, `backend/.env.example`: `AI_RANKING_ENABLED`.

## Kiểm thử

```powershell
Set-Location E:\vitech-ecommerce\backend
..\.venv\Scripts\python.exe -X utf8 -m pytest tests\test_ai_recommendation.py -q
```

`test_ai_recommendation.py` (16 test, SQLite riêng, model giả lập) kiểm tra:

- nhận diện nhu cầu;
- loại tiêu chí không hoạt động và chuẩn hóa trọng số;
- công thức B;
- thiếu dữ liệu không tính là đạt, camera không chấm theo MP, ổ cứng không ghi loại/HDD;
- T, H và không đẩy sản phẩm đã mua; quy tắc đồng điểm;
- lọc cứng loại sản phẩm vượt ngân sách/hết hàng; đúng điểm theo công thức;
- thẻ sắp theo điểm dù model liệt kê khác, dòng lý do đúng dữ liệu, `AiRanking` lưu nội bộ và không trả cho khách;
- hãng ưu tiên mềm; nhóm con mang tên nhu cầu không còn là bộ lọc cứng;
- “rẻ nhất” và chế độ baseline không bị sắp lại; không có tiêu chí thì giữ thứ tự; không có kết quả thì không xếp hạng cố;
- tải chi tiết theo lô giống tải từng sản phẩm, kể cả giá sau khuyến mãi tự động.

`test_ai_personalization.py` cập nhật: sản phẩm khách đã mua không còn được đẩy lên.

Kết quả xác minh sau khi chuyển Gemini xem [10.7](stage10-ai-evaluation.md). Công thức ranking chạy tại backend và không phụ thuộc SDK của model.

## Giới hạn

- Trọng số và ngưỡng chưa được hiệu chỉnh bằng dữ liệu; cần đo ở 10.7 (so với baseline, theo nhóm câu hỏi).
- Chỉ chấm 20 ứng viên đầu tiên theo thứ tự catalog (giá tăng dần) sau lọc cứng; khi có nhiều hơn 20 sản phẩm đạt, mẫu đắt hơn nằm ngoài 20 sẽ không được chấm (ví dụ câu chơi game ở trên).
- Nhận diện nhu cầu và CPU/GPU dựa trên mẫu văn bản tiếng Việt/tên chip phổ biến; cách viết thông số mới cần bổ sung mẫu và test.
- Thông số catalog chưa đồng nhất (tần số quét, khối lượng laptop hầu như không có), nên nhiều sản phẩm cùng bị “chưa có dữ liệu” ở các tiêu chí đó.
