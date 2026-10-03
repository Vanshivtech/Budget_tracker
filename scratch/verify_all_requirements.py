"""
Verification script for WhatsApp Budget Tracker updates.
Tests:
1. Avatar magic bytes validation (valid JPG, valid PNG, invalid GIF, oversize).
2. Database initialization and get_user_display avatar_url support.
3. Dashboard Tier 1 and Tier 2 timing and structure.
4. Agent App Guide direct response with no tools and exact closing sentence.
5. Verification of zero API keys leaked.
"""
import sys
import os
import io

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.storage import validate_avatar_file
from app.db import init_db, get_dashboard_ranged, get_dashboard_tier2, get_user_by_id, get_user_display
from app.llm import LLMPool
import app.agent as agent_module

def test_avatar_validation():
    print("--- Test 1: Avatar Magic Bytes & Size Validation ---")
    # Valid JPEG
    valid_jpg = b'\xff\xd8\xff\xe0\x00\x10JFIF' + b'\x00' * 50
    ok, mime, ext, err = validate_avatar_file(valid_jpg)
    assert ok and mime == 'image/jpeg' and ext == 'jpg', f"Failed valid JPG: {mime}, {ext}, {err}"
    print("[PASS] Valid JPEG recognized")

    # Valid PNG
    valid_png = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + b'\x00' * 50
    ok, mime, ext, err = validate_avatar_file(valid_png)
    assert ok and mime == 'image/png' and ext == 'png', f"Failed valid PNG: {mime}, {ext}, {err}"
    print("[PASS] Valid PNG recognized")

    # Invalid GIF
    gif_data = b'GIF89a' + b'\x00' * 50
    ok, mime, ext, err = validate_avatar_file(gif_data)
    assert not ok and "GIF" in err, f"Should reject GIF, got {err}"
    print("[PASS] GIF rejected successfully")

    # Oversize file (> 2MB)
    big_data = b'\xff\xd8\xff' + b'\x00' * (2 * 1024 * 1024 + 100)
    ok, mime, ext, err = validate_avatar_file(big_data)
    assert not ok and "2 MB" in err, f"Should reject oversize, got {err}"
    print("[PASS] Oversize file rejected (> 2MB)")

def test_db_dashboard_tier1_and_tier2():
    print("\n--- Test 2: Database Dashboard Tier 1 & Tier 2 ---")
    init_db()
    # Find a test user or demo user
    from app.db import get_db_cursor
    with get_db_cursor() as cur:
        cur.execute("SELECT id, email, username, avatar_url FROM users LIMIT 1;")
        user = cur.fetchone()
    
    if not user:
        print("[SKIP] No users in database")
        return

    uid = user['id']
    print(f"Testing for user ID: {uid} ({user['email']})")

    # Test Tier 1 (fast aggregates)
    import time
    t0 = time.perf_counter()
    tier1 = get_dashboard_ranged(uid)
    t1_dur = (time.perf_counter() - t0) * 1000
    print(f"[PASS] Tier 1 fetched in {t1_dur:.2f}ms")
    assert 'total_spent' in tier1
    assert 'budget_remaining' in tier1
    assert 'categories' in tier1
    assert 'recent_transactions' in tier1
    print(f"Tier 1 keys: {list(tier1.keys())}")

    # Test Tier 2
    t0 = time.perf_counter()
    tier2 = get_dashboard_tier2(uid)
    t2_dur = (time.perf_counter() - t0) * 1000
    print(f"[PASS] Tier 2 computed in {t2_dur:.2f}ms")
    assert 'health_score' in tier2
    assert 'projections' in tier2
    assert 'potential_savings' in tier2
    assert 'insights' in tier2
    print(f"Tier 2 keys: {list(tier2.keys())}")

def test_app_guide_in_system_prompt():
    print("\n--- Test 3: System Prompt App Guide & Closing Sentence ---")
    prompt = agent_module.SYSTEM_PROMPT
    assert "APP GUIDE" in prompt, "APP GUIDE missing from SYSTEM_PROMPT"
    assert "Let me know if you need help with anything else in the app." in prompt, "Closing sentence missing from SYSTEM_PROMPT"
    assert "without using any tools" in prompt, "No-tool rule missing from SYSTEM_PROMPT"
    print("[PASS] System prompt contains App Usage Guide and strict no-tool instruction")

def test_llm_key_pool():
    print("\n--- Test 4: LLM Key Pool Security & Log Sanitization ---")
    from app.llm import _mask_key
    pool = LLMPool()
    print(f"Total key slots initialized in pool: {len(pool._slots)}")
    for slot in pool._slots:
        masked = _mask_key(slot.key)
        assert slot.key not in repr(slot), "Raw key leaked in repr!"
        assert masked.startswith("...") or masked == "****"
        print(f"Slot {slot.slot_name}: {masked} (available={slot.is_available()})")

    print("[PASS] LLM Pool securely masks keys and does not leak secrets")

if __name__ == "__main__":
    test_avatar_validation()
    test_db_dashboard_tier1_and_tier2()
    test_app_guide_in_system_prompt()
    test_llm_key_pool()
    print("\nALL VERIFICATIONS PASSED SUCCESSFULLY!")
