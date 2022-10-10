import { Logo } from "@src/components/Logo";
import { Greeting } from "@src/components/Greeting";

export function MainMenu() {
  return (
    <>
      <div className="main-menu">
        <Logo />
        <div className="overlap-group">
          <div className="overlap-group1">
            <div className="rectangle-2"></div>
            <div className="cameras ubuntu-medium-white-12px">cameras</div>
          </div>
          <div className="notifications">settings</div>
        </div>
        <div className="rectangle-146">
          <Greeting />
        </div>
      </div>
    </>
  );
}
