import etvrLogo from "/images/logo.png";

export function Logo() {
  return (
    <div className="eyetrackvr-logo-gif-1">
      <div className="eyetrackvr-logo-gif-1-image">
        <img src={etvrLogo} alt="eytrackvrlogo" height="90px" width="90px" />
        <p className="notificationsDiv">
          4
        </p>
      </div>
    </div>
  );
}
