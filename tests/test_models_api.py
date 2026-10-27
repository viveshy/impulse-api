"""Model DTOs carry the listing extras; the detail view adds the verbatim spec."""


def test_model_detail_has_extras_and_spec(client, guids):
    r = client.get(f"/v1/models/{guids['opus_bedrock_gov']}").json()
    assert r["route"] == "us-gov-east-1" and r["spec"]["litellm_provider"] == "bedrock_converse"
    assert "id" not in r and "internal_id" not in r


def test_catalog_rows_have_extras(client):
    m = client.get("/v1/catalog").json()["models"][0]
    assert {"route", "features", "deprecationDate"} <= m.keys() and "batchInputPerMtok" in m["pricing"]


def test_model_detail_real_shaped_extras(client, guids):
    r = client.get(f"/v1/models/{guids['gpt_azure_eu']}").json()
    assert r["route"] == "eu" and r["litellmProvider"] == "azure"
    assert r["deprecationDate"] == "2028-03-11"
    assert r["pricing"]["inputPerMtok"] == 2.4
    assert r["pricing"]["longContext"] == {"thresholdTokens": 272000, "inputPerMtok": 4.8,
                                           "outputPerMtok": 18.0, "cachedInputPerMtok": 0.48,
                                           "batchInputPerMtok": None, "batchOutputPerMtok": None}
    assert r["reasoningEfforts"] == ["none", "xhigh", "max"]
    assert r["rateLimits"] is None


def test_first_party_listing_has_no_route(client, guids):
    r = client.get(f"/v1/models/{guids['opus']}").json()
    assert r["route"] is None and r["litellmProvider"] == "anthropic"
    assert r["pricing"]["batchInputPerMtok"] == 2.0 and r["pricing"]["regionalUplift"] == 1.1
    assert "fastMode" in r["features"]


def test_internal_ids_and_spec_stay_out_of_lists(client):
    for rows in (client.get("/v1/catalog").json()["models"],
                 client.get("/v1/models?limit=100").json()["data"]):
        assert len(rows) == 4
        for m in rows:
            assert not {"spec", "id", "internal_id", "provider_slug", "model_spec"} & m.keys()
            assert {"route", "litellmProvider", "deprecationDate", "sourceUrl", "features",
                    "reasoningEfforts", "rateLimits"} <= m.keys()


def test_alternatives_still_work(client, guids):
    r = client.get(f"/v1/models/{guids['opus']}/alternatives")
    assert r.status_code == 200
    assert r.json()["target"]["route"] is None


def test_a_huge_page_number_is_rejected_not_a_500(client):
    # (page - 1) * limit has to fit SQLite's 64-bit OFFSET
    for path in ("/v1/models?page=922337203685477581", "/v1/providers?page=99999999999999999999"):
        assert client.get(path).status_code == 422, path
    r = client.get("/v1/models?page=1000000").json()
    assert r["data"] == [] and r["pagination"]["page"] == 1000000
