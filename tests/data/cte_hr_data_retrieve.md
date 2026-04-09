---
jupyter:
  jupytext:
    text_representation:
      extension: .md
      format_name: pandoc
      format_version: 3.5
      jupytext_version: 1.19.1
  kernelspec:
    display_name: verification-games-fluxes
    language: python
    name: verification-games-fluxes
  nbformat: 4
  nbformat_minor: 5
---

::: {#472c511c-3dee-461e-9d8d-57cfc735fe59 .cell .markdown}
# Getting CTE-HR fluxes

These are available from ICOS, just need to download them.
:::

::: {#e2a3631e-2697-4048-96cd-fc46ab911931 .cell .code}
``` python
# try to fix SSL issue
import os
os.environ["SSL_CERT_FILE"] = "/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem"
```
:::

::: {#32ce41d3-299f-44c8-97d3-c8c0b83da672 .cell .code}
``` python
from icoscp_core.icos import auth

auth.init_config_file()
```
:::

::: {#ca696c9c-8614-4e49-90e3-7788cae38e55 .cell .code}
``` python
from icoscp_core.icos import data, meta, ATMO_STATION
import pandas as pd
import numpy as np
```
:::

::: {#a5e2c604-e3c7-4161-92b9-482de1de9de8 .cell .code}
``` python
# from icoscp_core.icos import bootstrap

# cookie_token = !cat /user/work/bm13805/icos_token.txt
# meta, data = bootstrap.fromCookieToken(cookie_token[0])
```
:::

::: {#c47b4e76-48c8-4bfe-a36a-894f9800d611 .cell .markdown}
## Test download

Let\'s try to get one month. I should be able to download the data directly using the `icoscp_core` API
:::

::: {#d5698a00-cf36-46e2-9d61-fc6812c46cba .cell .code}
``` python
test_uri = "https://meta.icos-cp.eu/objects/O3Z-0pkbcIGz0lEI5f3I8n1z"
```
:::

::: {#b7bbe22a-fea0-46ab-a903-9dbe5582d856 .cell .code}
``` python
from dataclasses import asdict
from pprint import pprint

def dcprint(dc):
    pprint(asdict(dc))
```
:::

::: {#89e9491e-868b-4d33-9dfa-bc414d54adf1 .cell .code}
``` python
test_dobj = meta.get_dobj_meta(test_uri)
test_dobj
```
:::

::: {#50a9a3ad-dadc-4001-a12f-2c81bd0d0df4 .cell .code}
``` python
data.save_to_folder?
```
:::

::: {#f59869a1-f6df-49ea-b9d2-b926e6ad689a .cell .code}
``` python
!ls ../data/raw/
```
:::

::: {#09d6993a-0c31-44df-bab4-bd0447f64e42 .cell .code}
``` python
data.save_to_folder(test_uri, "../data/raw/cte_hr/")
```
:::

::: {#15fc8b1a-d2c1-4d0d-a120-c3eb66204ab9 .cell .code}
``` python
!ls ../data/raw/cte_hr
```
:::

::: {#64f37f0e-613a-4c29-b4a6-fef02521a8f1 .cell .code}
``` python
import xarray as xr

test_ds = xr.open_mfdataset(["../data/raw/cte_hr/anthropogenic.persector.202101.nc"])
test_ds
```
:::

::: {#befade26-e802-4fbb-9a25-32f59b92dc7a .cell .markdown}
Let\'s see if there is a faster way for just checking Public Power.
:::

::: {#5ee5e3e6-ad95-46df-b3f4-7de9c689f709 .cell .code}
``` python
data.get_file_stream?
```
:::

::: {#acbcca40-fb7d-4906-8b10-f8597e3d7fff .cell .code}
``` python
print(asdict(test_dobj.specificInfo).keys())
```
:::

::: {#7e6a44a4-b534-47aa-805b-7e491e4dabfd .cell .code}
``` python
print([v.label for v in test_dobj.specificInfo.variables])
```
:::

::: {#822f620f-7603-4a23-ad70-126fcb025185 .cell .code}
``` python
pubpow_arr = data.get_columns_as_arrays(test_dobj, columns = ["A_Public_power"])
```
:::

::: {#e3a97a9a-aacd-4325-8d50-d3584cd11663 .cell .markdown}
Okay seems like those methods only work for timeseries.
:::

::: {#5c2acbf2-2128-49c9-8132-24d1489928ef .cell .markdown}
## Searching for data

We need multiple URIs.
:::

::: {#bb626a3e-6b95-41b2-b6fd-9b540d009aff .cell .code}
``` python
data_types = meta.list_datatypes()
dt_df = pd.DataFrame([asdict(dt) for dt in data_types])
dt_df.head()
```
:::

::: {#0d9e03fa-19a6-40ea-9116-774d43cd52ce .cell .code}
``` python
dt_df.loc[dt_df.label.str.contains("Anthropogenic emission model")].iloc[0, 0]
```
:::

::: {#9883c70e-cd7f-4261-b1d6-3d587a9d8185 .cell .markdown}
Okay so we have the data type:
:::

::: {#2ec7dd7c-6189-451c-b33b-032f7faf6406 .cell .code}
``` python
cte_hr_data_type = dt_df.loc[dt_df.label.str.contains("Anthropogenic emission model")].iloc[0, 0]
```
:::

::: {#dc9a384a-ca6d-4a64-9f20-06f07714c96d .cell .markdown}
Here is the collection URI from the ICOS CP website:
:::

::: {#bf92b840-136a-4333-a5ab-b1b28d1fd58a .cell .code}
``` python
cte_hr_collection_uri = "https://meta.icos-cp.eu/collections/EhfdtxWwB7UG4zAhDjPFnZXB"
cte_hr_collection_uri_2021 = "https://meta.icos-cp.eu/collections/8GlHwayg9wycYRMsoDPRrPDR"
```
:::

::: {#02ec6b23-fa9b-40f2-bd80-6f788b32ca7f .cell .code}
``` python
cte_hr_collection = meta.get_collection_meta(cte_hr_collection_uri)
print(asdict(cte_hr_collection).keys())
```
:::

::: {#6c752ef7-f7f6-4031-934e-d890782c80de .cell .code}
``` python
cte_hr_collection.members
```
:::

::: {#122cc242-62cd-43c4-a1f9-0e0479a7ea4d .cell .code}
``` python
cte_hr_2017 = meta.get_collection_meta(cte_hr_collection.members[0].res)
print(asdict(cte_hr_2017).keys())
```
:::

::: {#5047fccc-bcf6-45d4-a085-17a84b800865 .cell .code}
``` python
cte_hr_2017.members
```
:::

::: {#51538cb9-c1bb-4002-8396-087fd47cf389 .cell .code}
``` python
cte_hr_2017_01 = meta.get_collection_meta(cte_hr_2017.members[0].res)
print(asdict(cte_hr_2017_01).keys())
```
:::

::: {#0d1a0435-8cc4-4a83-998e-35b1734e3c52 .cell .code}
``` python
cte_hr_2017_01.members
```
:::

::: {#27e0edc4-c652-4f39-a745-15cc8bcf347e .cell .code}
``` python
cte_hr_2017_01_anthro_sect = meta.get_dobj_meta(cte_hr_2017_01.members[1].res)
print(asdict(cte_hr_2017_01_anthro_sect).keys())
```
:::

::: {#50ded4e9-57c7-4a12-b081-c242ac70a32b .cell .code}
``` python
print(asdict(cte_hr_2017_01_anthro_sect.specificInfo).keys())
```
:::

::: {#0e303a3e-d530-4f30-9451-1a5e1e7a3ccf .cell .markdown}
## Trying to get all the URIs for a year
:::

::: {#56df464c-9321-4aee-bb77-b228591b5782 .cell .code}
``` python
from icoscp_core.icos import meta

TOP_COLLECTION = "https://meta.icos-cp.eu/collections/EhfdtxWwB7UG4zAhDjPFnZXB"

def get_cte_urls(year: int) -> list:
    top = meta.get_collection_meta(TOP_COLLECTION)

    year_coll = next(
        coll for coll in top.members
        if str(year) in coll.title
    )

    year_coll_meta = meta.get_collection_meta(year_coll.res)

    results = []
    for month_coll in year_coll_meta.members:
        month_meta = meta.get_collection_meta(month_coll.res)

        for obj in month_meta.members:
            dobj = meta.get_dobj_meta(obj.res)
            spec_info = dobj.specificInfo
            title = spec_info.title

            if (
                "anthropogenic emissions" in title.lower()
                and "per sector" in title.lower()
            ):
                results.append(dobj)
    return results
```
:::

::: {#825b8c48-5908-4385-9ce1-7cbf8e09e003 .cell .code}
``` python
cte_urls_2021 = get_cte_urls(2021)
```
:::

::: {#54f69c01-11f7-489b-a3d9-e175d99a9685 .cell .code}
``` python
print(pd.DataFrame([asdict(dobj) for dobj in cte_urls_2021])[["accessUrl", "fileName"]])
```
:::

::: {#d7420333-4ee1-4090-a66a-87a1f7e3e262 .cell .code}
``` python
print(asdict(cte_urls_2021[0]))
```
:::

::: {#bd7142c0-abca-4a92-8d50-278db36f89ba .cell .code}
``` python
data.get_file_stream??
```
:::

::: {#50f1576a-d306-429e-8e97-cc05ec489c87 .cell .code}
``` python
from icoscp_core.http import http_request
from icoscp_core.auth import http_auth_request
```
:::

::: {#b669cd67-6b19-4f2e-91ae-803edcbce3ba .cell .code}
``` python
http_auth_request??
```
:::

::: {#dd981dbf-d60a-46db-be99-b95dd2e32d5b .cell .code}
``` python
http_request??
```
:::

::: {#8650b820-d7d4-4523-bae7-0f60e7857390 .cell .code}
``` python
from icoscp_core.cpb import to_dobj_uri
to_dobj_uri??
```
:::

::: {#7e185b62-a89e-46f0-bb40-e62c9112e811 .cell .code}
``` python
data._auth._provider.save_to_file??
```
:::

::: {#94ed49b5-32c6-4a9f-8104-e9d0fa69c95b .cell .code}
``` python
data._auth._conf_file_path
```
:::

::: {#2d6b3aa3-d376-4b26-83c7-d55336f44507 .cell .markdown}
## Downloading data
:::

::: {#ffbab0fc-80d9-436d-8c05-3a6fc1a22f33 .cell .code}
``` python
from pathlib import Path

out_path = Path("../data/raw/cte_hr/")
```
:::

::: {#96b2c004-4dac-418e-a3e2-d20b9fe4981d .cell .code}
``` python
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

from icoscp_core.icos import data


@dataclass(frozen=True)
class DownloadResult:
    """Result of one download attempt."""
    file_name: str
    output_path: Path
    status: str  # "downloaded", "skipped", or "error"
    source_uri: str
    error: str | None = None


def access_url_to_meta_uri(access_url: str) -> str:
    """Convert a data download URL to the corresponding meta landing-page URI.

    This assumes the host changes from data.icos-cp.eu to meta.icos-cp.eu,
    while the path stays the same.
    """
    parts = urlsplit(access_url)
    netloc = parts.netloc.replace("data.icos-cp.eu", "meta.icos-cp.eu")
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


def get_dobj_uri(dobj: Any) -> str:
    """Return the landing-page URI for a Dobj-like object.

    Preference order:
    1. `res` attribute, if present
    2. derive from `accessUrl`
    """
    res = getattr(dobj, "res", None)
    if res:
        return str(res)

    access_url = getattr(dobj, "accessUrl", None)
    if not access_url:
        raise ValueError(f"Object has neither 'res' nor 'accessUrl': {dobj!r}")

    return access_url_to_meta_uri(str(access_url))


def download_one_dobj(
    dobj: Any,
    output_dir: Path,
    force_retrieve: bool = False,
    chunk_size: int = 4 * 1024 * 1024,
    use_save_to_folder: bool = False,
) -> DownloadResult:
    """Download one ICOS object to `output_dir`.

    Parameters
    ----------
    dobj
        Dobj-like object with at least `.fileName` and `.accessUrl`, optionally `.res`.
    output_dir
        Directory to write files into.
    force_retrieve
        If False, skip download when the target file already exists.
        If True, re-download and overwrite.
    chunk_size
        Chunk size for streamed writing when using `get_file_stream`.
    use_save_to_folder
        If True, use `data.save_to_folder(...)` for retrieval.
        If False, use `data.get_file_stream(...)` and stream to disk.

    Returns
    -------
    DownloadResult
        Status for this file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    file_name = str(getattr(dobj, "fileName"))
    output_path = output_dir / file_name
    source_uri = get_dobj_uri(dobj)

    if output_path.exists() and not force_retrieve:
        return DownloadResult(
            file_name=file_name,
            output_path=output_path,
            status="skipped",
            source_uri=source_uri,
        )

    try:
        if use_save_to_folder:
            # save_to_folder overwrites if the file exists, which is what we want
            # when force_retrieve=True or the file does not yet exist.
            saved_name = data.save_to_folder(source_uri, str(output_dir))
            saved_path = output_dir / saved_name
            return DownloadResult(
                file_name=saved_name,
                output_path=saved_path,
                status="downloaded",
                source_uri=source_uri,
            )

        # Streamed variant.
        filename_from_server, response = data.get_file_stream(source_uri)

        # Prefer the local metadata filename if present; it should usually match.
        target_path = output_path
        if not file_name and filename_from_server:
            target_path = output_dir / filename_from_server

        try:
            with target_path.open("wb") as f:
                while True:
                    chunk = response.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
        finally:
            response.close()

        return DownloadResult(
            file_name=target_path.name,
            output_path=target_path,
            status="downloaded",
            source_uri=source_uri,
        )

    except Exception as exc:
        return DownloadResult(
            file_name=file_name,
            output_path=output_path,
            status="error",
            source_uri=source_uri,
            error=str(exc),
        )


def download_dobjs_threaded(
    dobjs: Iterable[Any],
    output_path: str | Path,
    *,
    force_retrieve: bool = False,
    max_workers: int = 4,
    chunk_size: int = 4 * 1024 * 1024,
    use_save_to_folder: bool = False,
    raise_on_error: bool = False,
) -> list[DownloadResult]:
    """Download multiple ICOS objects concurrently.

    Parameters
    ----------
    dobjs
        Iterable of Dobj-like objects with `.fileName` and `.accessUrl`,
        optionally `.res`.
    output_path
        Target directory.
    force_retrieve
        Re-download even if the target file already exists.
    max_workers
        Number of worker threads.
    chunk_size
        Chunk size in bytes for streamed downloads.
    use_save_to_folder
        If True, use `data.save_to_folder`. Otherwise use `data.get_file_stream`.
    raise_on_error
        If True, raise an exception if any download fails.

    Returns
    -------
    list[DownloadResult]
        One result per input object, in completion order.
    """
    output_dir = Path(output_path)
    dobj_list = list(dobjs)
    results: list[DownloadResult] = []

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                download_one_dobj,
                dobj,
                output_dir,
                force_retrieve,
                chunk_size,
                use_save_to_folder,
            ): dobj
            for dobj in dobj_list
        }

        for future in as_completed(futures):
            result = future.result()
            results.append(result)

    if raise_on_error:
        errors = [r for r in results if r.status == "error"]
        if errors:
            msgs = "\n".join(f"{r.file_name}: {r.error}" for r in errors)
            raise RuntimeError(f"One or more downloads failed:\n{msgs}")

    return results
```
:::

::: {#26d6657f-814d-426e-a33c-02599000a069 .cell .code}
``` python
results = download_dobjs_threaded(
    cte_urls_2021,
    output_path=out_path,
    force_retrieve=False,
    max_workers=4,
    chunk_size=4 * 1024 * 1024,
    use_save_to_folder=False,
)

for r in results:
    print(r.status, r.output_path)
    if r.error:
        print("  error:", r.error)
```
:::

::: {#8c6481fa-13d8-4fa5-982f-44a1d463df8f .cell .code}
``` python
```
:::
