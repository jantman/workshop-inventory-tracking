# Contract: What the Reverse Proxy Must Declare

**Feature**: `specs/023-restore-forwarded-port/` | **Date**: 2026-08-21

This application's only external interface that is not a browser page is the one it has with the
reverse proxy in front of it. That interface is a set of request headers, and it has always been a
contract — it was simply never written as one, only described in prose in the deployment guide. This
feature adds a term to it, which is a good moment to write the terms down.

The consequence column is observed, not predicted: each was reproduced by the Phase 0 probe in
[research.md](research.md).

## Why there is a contract at all

The application does not receive the request the browser made. It receives a plain-HTTP request from
the proxy, on the LAN, whose scheme, host, port and client address are all the proxy's rather than
the browser's. Everything the application knows about the real request, it knows because the proxy
told it.

It trusts exactly **one hop** of these declarations. That is not a security control — the deployment
is single-user and LAN-only, and there is nobody to spoof a header. The one-hop setting exists so the
addresses come out right.

## Terms

| Header | Required | Must carry | If absent or wrong |
|---|---|---|---|
| `X-Forwarded-Proto` | yes | the scheme the browser used — `https` where TLS is terminated at the proxy | The application believes it is on `http`. The capture page shows its "not served over https" warning at an `https` address bar, and the bookmarklet hands out `http` addresses that a vendor page's `upgrade-insecure-requests` rewrites and breaks. This is issue #89. |
| `X-Forwarded-Host` | yes | the host the browser used | The application believes it is at the container's own name, which is no use to a browser on the LAN. |
| **`X-Forwarded-Port`** | **yes — new in this feature** | **the port the browser used** | **The application believes it is on the scheme's default port. Every secure form submission is refused with `400 Bad Request — The referrer does not match the host`, and the bookmarklet points at a port nothing listens on. This is issue #114.** |
| `X-Forwarded-For` | yes | the browser's address | Logs attribute every request to the proxy. Cosmetic. |

## Obligations on the application

1. Honour each declaration for exactly one hop.
2. Omit a port from any address it builds when that port is the scheme's default — so a proxy may
   declare `443` on `https` or `80` on `http` unconditionally, without producing `https://host:443/`.
   Werkzeug already does this; the application adds nothing.
3. Discard a port declaration that is not a plain decimal number, and fall back to the host that
   arrived. Without this the application composes a host containing invalid characters, which
   collapses to the **empty string** and makes every address it builds malformed.
4. Behave exactly as it does on a direct connection when no declaration is present. This is the
   development server's case and the end-to-end suite's case, and it must not move.

## Reference configuration

```nginx
location / {
    proxy_pass http://workshop-inventory:5000;
    proxy_set_header Host              $host;
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header X-Forwarded-Host  $host;
    proxy_set_header X-Forwarded-Port  $server_port;   # new: issue #114
    proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
}
```

`$server_port` is the port the proxy itself is listening on, which is the port the browser connected
to. It is always numeric, so obligation 3 above is never exercised by this configuration — it exists
for the deployment that does not use it.

`$host` deliberately excludes the port; the port travels in its own header. A proxy that instead
sends `X-Forwarded-Host $http_host` — with the port inside the host — also satisfies this contract,
and was observed to work both before and after this feature. It is not the recommended form, because
it works by accident of what `$http_host` happens to contain rather than by stating the port where
the contract says the port goes.

## Verifying the contract holds

Load `/products/capture` over `https` on the deployment and read the bookmarklet's `href`. It
contains the two addresses the application built from these declarations. If both carry the correct
scheme, host **and** port, all four terms are being met. If they do not, the header that is missing
is named by the mismatch: wrong scheme, wrong host, or missing port.
