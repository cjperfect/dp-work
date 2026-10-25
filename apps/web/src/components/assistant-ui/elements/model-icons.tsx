import { siAnthropic, siGooglegemini } from "simple-icons";
import type { FC, SVGProps } from "react";

/** OpenAI 官方 Logo path（simple-icons 曾收录的开源数据，品牌色随上下文） */
const OPENAI_PATH =
  "M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5145 2.9001A5.985 5.985 0 0 0 13.2599 24a6.0554 6.0554 0 0 0 5.7718-4.2058 5.989 5.989 0 0 0 3.9977-2.9001 6.0554 6.0554 0 0 0-.7475-7.073zm-5.53 2.0712a3.8715 3.8715 0 0 1-.3495 3.1794 3.9228 3.9228 0 0 1-4.2176 1.8769 3.9055 3.9055 0 0 1-2.6112-2.5864 3.8861 3.8861 0 0 1 .4663-3.6474 3.906 3.906 0 0 1 4.2183-1.8795 3.9021 3.9021 0 0 1 2.6112 2.5865 3.9055 3.9055 0 0 1-.118 2.4706z";

type BrandIconProps = SVGProps<SVGSVGElement> & {
  path: string;
  color?: string;
};

const BrandIcon: FC<BrandIconProps> = ({ path, color, ...rest }) => (
  <svg viewBox="0 0 24 24" fill={color ?? "currentColor"} aria-hidden="true" {...rest}>
    <path d={path} />
  </svg>
);

/** OpenAI 品牌图标 */
export const OpenAILogo: FC<SVGProps<SVGSVGElement>> = (props) => (
  <BrandIcon path={OPENAI_PATH} {...props} />
);

/** Anthropic / Claude 品牌图标 */
export const ClaudeLogo: FC<SVGProps<SVGSVGElement>> = (props) => (
  <BrandIcon path={siAnthropic.path} color="#D97757" {...props} />
);

/** Google Gemini 品牌图标 */
export const GeminiLogo: FC<SVGProps<SVGSVGElement>> = (props) => (
  <BrandIcon path={siGooglegemini.path} color={`#${siGooglegemini.hex}`} {...props} />
);
