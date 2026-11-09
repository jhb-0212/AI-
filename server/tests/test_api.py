"""接口层的测试：登录、权限、CRUD、slug 冲突。"""


def test_health(client):
    assert client.get("/api/health").json()["ok"] is True


def test_requires_login(client):
    assert client.get("/api/posts").status_code == 401
    assert client.get("/api/albums").status_code == 401


def test_login_rejects_wrong_password(client):
    res = client.post("/api/auth/login", json={"username": "admin", "password": "nope"})
    assert res.status_code == 401
    # 不区分「用户不存在」和「口令错」，避免被拿去试账号
    assert res.json()["detail"] == "用户名或口令不对"


def test_login_and_me(admin):
    assert admin.get("/api/auth/me").json()["username"] == "admin"


def test_seed_imported_existing_content(admin):
    posts = admin.get("/api/posts").json()
    slugs = {p["slug"] for p in posts}
    assert {"opening", "ai-colleague", "fifteen-seconds"} <= slugs

    novels = admin.get("/api/novels").json()
    novel = next(n for n in novels if n["slug"] == "kuajie-zhufu")
    # 作品 md 的 frontmatter 后面那段说明不能丢
    assert "AIGC 漫剧" in novel["body"]

    chapters = admin.get(f"/api/novels/{novel['slug']}/chapters").json()
    assert [c["order"] for c in chapters] == [1, 2]

    site = admin.get("/api/site").json()
    assert site["name"] == "忘忧居"
    assert len(site["tracks"]) >= 5


def test_post_crud_and_slug_conflict(admin):
    payload = {
        "slug": "test-post",
        "title": "测试文章",
        "date": "2026-11-07",
        "tag": "测试",
        "read_time": "2 分钟",
        "summary": "只为测试。",
        "body": "第一段。",
        "draft": False,
    }
    res = admin.post("/api/posts", json=payload)
    assert res.status_code == 201
    post_id = res.json()["id"]

    assert admin.post("/api/posts", json=payload).status_code == 409

    payload["title"] = "改过的标题"
    updated = admin.put(f"/api/posts/{post_id}", json=payload)
    assert updated.status_code == 200 and updated.json()["title"] == "改过的标题"

    assert admin.delete(f"/api/posts/{post_id}").status_code == 204
    assert admin.get(f"/api/posts/{post_id}").status_code == 404


def test_slug_must_be_url_safe(admin):
    res = admin.post(
        "/api/posts",
        json={"slug": "中文标题", "title": "x", "date": "2026-11-07"},
    )
    assert res.status_code == 400


def test_novel_chapter_crud(admin):
    novel = {
        "slug": "test-novel",
        "title": "测试作品",
        "subtitle": "副标题",
        "summary": "简介",
        "status": "连载中",
        "tags": ["测试"],
        "updated": "2026-11-07",
        "body": "",
        "draft": False,
    }
    assert admin.post("/api/novels", json=novel).status_code == 201
    assert admin.post("/api/novels", json=novel).status_code == 409

    ch = {"slug": "ch-01", "title": "第一章", "order": 1, "date": "2026-11-07", "body": "正文"}
    assert admin.post("/api/novels/test-novel/chapters", json=ch).status_code == 201
    assert admin.post("/api/novels/test-novel/chapters", json=ch).status_code == 409

    # 改作品 slug，章节目录要跟着改
    target = next(n for n in admin.get("/api/novels").json() if n["slug"] == "test-novel")
    novel["slug"] = "test-novel-2"
    assert admin.put(f"/api/novels/{target['id']}", json=novel).status_code == 200

    chapters = admin.get("/api/novels/test-novel-2/chapters").json()
    assert chapters and chapters[0]["novel_slug"] == "test-novel-2"

    assert admin.delete(f"/api/novels/{target['id']}").status_code == 204
    assert admin.get("/api/novels/test-novel-2/chapters").json() == []


def test_album_and_track_flow(admin):
    album = {"slug": "test-album", "title": "测试相册", "tone": "cyan", "note": "", "sort": 0}
    assert admin.post("/api/albums", json=album).status_code == 201
    albums = admin.get("/api/albums").json()
    created = next(a for a in albums if a["slug"] == "test-album")
    assert admin.delete(f"/api/albums/{created['id']}").status_code == 204

    track = {"netease_id": 64638, "name": "测试曲目", "artist": "x", "dur": 100, "why": "", "sort": 99}
    assert admin.post("/api/site/tracks", json=track).status_code == 201
    tracks = admin.get("/api/site/tracks").json()
    tid = next(t["id"] for t in tracks if t["name"] == "测试曲目")
    assert admin.delete(f"/api/site/tracks/{tid}").status_code == 204


def test_album_rejects_non_image(admin):
    albums = admin.get("/api/albums").json()
    slug = albums[0]["slug"]
    res = admin.post(
        f"/api/albums/{slug}/photos",
        files={"file": ("evil.txt", b"not an image", "text/plain")},
    )
    assert res.status_code == 400
