import { Logo } from "@src/components/Logo";

export function MainMenu({ handleNavChange, state }) {
    return (
        <>
            <div className="main_menu">
                <Logo />
                <div className="navbar_container">
                    <div className="navbar_group">
                        <div onClick={handleNavChange} className="navbar_item">
                            <div
                                className={
                                    state.dashboard
                                        ? "dashboard_highlight"
                                        : "highlight_inactive"
                                }
                            />
                            <div
                                className={
                                    state.dashboard
                                        ? "nav_item_active"
                                        : "nav_item_inactive"
                                }
                            >
                                <span>dashboard</span>
                            </div>
                        </div>
                    </div>
                    <div className="navbar_group">
                        <div onClick={handleNavChange} className="navbar_item">
                            <div
                                className={
                                    state.settings
                                        ? "settings_highlight"
                                        : "highlight_inactive"
                                }
                            />
                            <div
                                className={
                                    state.settings
                                        ? "nav_item_active"
                                        : "nav_item_inactive"
                                }
                            >
                                <span>settings</span>
                            </div>
                        </div>
                    </div>
                </div>
                <div className="rectangle_146" />
            </div>
        </>
    );
}
