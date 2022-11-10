import etvrLogo from "/images/logo.png";
export function Logo() {
    return (
        <div className="eyetrackvr_logo_gif_1">
            <div className="eyetrackvr_logo_gif_1_image">
                <img
                    src={etvrLogo}
                    alt="eytrackvrlogo"
                    height="90px"
                    width="90px"
                />
                <p className="notifications_div">4</p>
            </div>
        </div>
    );
}
