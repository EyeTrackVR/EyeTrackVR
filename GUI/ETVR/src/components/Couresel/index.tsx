import Slider from './Slider'
import Slide from './Slider/Slide'
import useSlider from './Slider/useSlider'

export default function MyComponent() {
  const { setSliderLength, slideIndex, isRight, slideLeft, goToIndex, slideRight, slideArray } =
    useSlider()

  return (
    <div className="flex flex-col items-center py-16">
      <div className="h-32 w-32">
        <Slider setSliderLength={setSliderLength}>
          <Slide index={0} currentIndex={slideIndex} isRight={isRight}>
            <div className="h-full w-full absolute rounded-md bg-pink-600 shadow-lg" />
          </Slide>

          <Slide index={1} currentIndex={slideIndex} isRight={isRight}>
            <div className="h-full w-full absolute rounded-md bg-blue-600 shadow-lg" />
          </Slide>

          <Slide index={2} currentIndex={slideIndex} isRight={isRight}>
            <div className="h-full w-full absolute rounded-md bg-black shadow-lg" />
          </Slide>
        </Slider>
      </div>

      <div className="flex mt-5">
        <button
          onClick={() => slideLeft()}
          className="backface-visibility-hidden mx-2 flex transform items-center rounded-full bg-black bg-opacity-20 w-8 h-8 text-sm font-medium text-white transition hover:scale-105 hover:bg-opacity-30 focus:outline-none active:bg-opacity-40">
          <span className="mx-auto">←</span>
        </button>

        {slideArray.map((index) => (
          <button
            key={index}
            onClick={() => goToIndex(index)}
            className={`${
              slideIndex === index ? 'bg-gray-400' : 'bg-black'
            } backface-visibility-hidden mx-2 flex transform items-center rounded-full bg-opacity-20 w-8 h-8 text-sm font-medium text-white transition hover:scale-105 hover:bg-opacity-30 focus:outline-none active:bg-opacity-40`}>
            <span className="mx-auto">&#x2022;</span>
          </button>
        ))}

        <button
          onClick={() => slideRight()}
          className="backface-visibility-hidden mx-2 flex transform items-center rounded-full bg-black bg-opacity-20 w-8 h-8 text-sm font-medium text-white transition hover:scale-105 hover:bg-opacity-30 focus:outline-none active:bg-opacity-40">
          <span className="mx-auto">→</span>
        </button>
      </div>
    </div>
  )
}
