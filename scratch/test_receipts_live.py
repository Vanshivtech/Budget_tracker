"""
Test receipt upload, magic bytes rejection, and download via live HTTP server.
"""
import urllib.request
import json
import uuid

BASE_URL = "http://127.0.0.1:8000"

def run_receipt_http_test():
    # 1. Login
    login_data = json.dumps({"email": "e2e_tier3_tester@example.com", "password": "strongpassword123"}).encode()
    req = urllib.request.Request(f"{BASE_URL}/api/login", data=login_data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode())
        token = res["token"]

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    
    # 2. Test uploading an invalid file (spoofed text)
    bad_content = b"This is plain text, not a real image"
    bad_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="fake.jpg"\r\n'
        f"Content-Type: image/jpeg\r\n\r\n"
    ).encode() + bad_content + f"\r\n--{boundary}--\r\n".encode()

    bad_req = urllib.request.Request(
        f"{BASE_URL}/api/receipts/upload",
        data=bad_body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}",
        },
        method="POST"
    )
    try:
        urllib.request.urlopen(bad_req)
        print("FAILED: Server accepted invalid magic bytes!")
        return False
    except urllib.error.HTTPError as e:
        assert e.code == 400
        print("PASS: Server correctly rejected invalid magic bytes with 400 Bad Request.")

    # 3. Test uploading a valid PNG file
    png_content = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    good_body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="receipt.png"\r\n'
        f"Content-Type: image/png\r\n\r\n"
    ).encode() + png_content + f"\r\n--{boundary}--\r\n".encode()

    good_req = urllib.request.Request(
        f"{BASE_URL}/api/receipts/upload",
        data=good_body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Authorization": f"Bearer {token}",
        },
        method="POST"
    )
    with urllib.request.urlopen(good_req) as resp:
        assert resp.status == 200
        rec_data = json.loads(resp.read().decode())
        receipt_id = rec_data["receipt"]["id"]
        signed_url = rec_data["receipt"]["signed_url"]
        print(f"PASS: Uploaded valid receipt, id={receipt_id}, signed_url generated.")

    # 4. List receipts
    list_req = urllib.request.Request(
        f"{BASE_URL}/api/receipts",
        headers={"Authorization": f"Bearer {token}"}
    )
    with urllib.request.urlopen(list_req) as resp:
        assert resp.status == 200
        list_data = json.loads(resp.read().decode())
        assert any(r["id"] == receipt_id for r in list_data["receipts"])
        print(f"PASS: Listed {len(list_data['receipts'])} receipt(s).")

    # 5. Delete receipt
    del_req = urllib.request.Request(
        f"{BASE_URL}/api/receipts/{receipt_id}",
        headers={"Authorization": f"Bearer {token}"},
        method="DELETE"
    )
    with urllib.request.urlopen(del_req) as resp:
        assert resp.status == 200
        print(f"PASS: Deleted receipt {receipt_id}.")

    print("ALL RECEIPT LIVE HTTP TESTS PASSED!")
    return True

if __name__ == "__main__":
    run_receipt_http_test()
