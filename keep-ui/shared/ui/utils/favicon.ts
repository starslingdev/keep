export function setFavicon(status: string) {
  const favicon: HTMLLinkElement | null =
    document.querySelector('link[rel="icon"]');
  if (!favicon) {
    return;
  }

  switch (status) {
    case "success":
      favicon.href = "/continuum-success.svg";
      break;
    case "failure":
      favicon.href = "/continuum-failure.svg";
      break;
    case "pending":
      favicon.href = "/continuum-pending.svg";
      break;
    default:
      favicon.href = "/icon.svg";
  }
}
