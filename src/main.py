import os
from ipaddress import IPv4Address

from waitress import serve

from app import create_web_app


def main() -> None:
    """Main entry point for the application."""
    app = create_web_app()

    # Start the application server
    threads_env = os.environ.get("SERVER_THREADS")
    try:
        threads = int(threads_env) if threads_env is not None else 1
    except ValueError:
        threads = 1

    # Waitress string-matches one immediate peer, so the value must be in the
    # canonical form REMOTE_ADDR takes. The server binds IPv4 only.
    #
    # "*" trusts every peer. That is meant for running behind several proxies
    # at once (e.g. Tailscale Funnel via the Docker gateway plus a NetBird
    # reverse proxy whose address can change), and is acceptable only because
    # the port must never be reachable publicly and just x-forwarded-proto is
    # trusted below: a peer can at most switch feed links between http and
    # https. X-Forwarded-For stays untrusted, so rate limits keep the socket
    # address.
    trusted_proxy = os.environ.get("PODLY_TRUSTED_PROXY", "").strip() or None
    if trusted_proxy is not None and trusted_proxy != "*":
        try:
            trusted_proxy = str(IPv4Address(trusted_proxy))
        except ValueError as exc:
            raise ValueError(
                "PODLY_TRUSTED_PROXY must be '*' or the IPv4 address of the "
                "immediate proxy peer"
            ) from exc

    port = os.environ.get("PORT", 5001)
    serve(
        app,
        host="0.0.0.0",
        port=port,
        threads=threads,
        trusted_proxy=trusted_proxy,
        # Preserve the socket peer used by authentication rate limits.
        trusted_proxy_headers={"x-forwarded-proto"} if trusted_proxy else set(),
        # A proxy whose address changed would otherwise silently revert to http.
        log_untrusted_proxy_headers=trusted_proxy is not None,
    )


if __name__ == "__main__":
    main()
