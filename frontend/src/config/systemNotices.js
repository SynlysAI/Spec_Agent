/**
 * 工作台系统公告配置。
 *
 * 直接维护该数组即可更新工作台右侧“系统公告”内容。
 */
export const SYSTEM_NOTICES = [
  {
    id: 'lcms-convert-service-unavailable',
    updatedAt: '2026-06-08 08:30',
    title: 'LCMS 数据转换工具服务暂时不可用',
    content:
      '由于 HW 服务器采用 ARM 架构，部分依赖无法安装，当前工具服务里的 LCMS 数据转换能力暂不可用。',
  },
]
