"""U-Net used by yakhyo/crack-segmentation.

Upstream: https://github.com/yakhyo/crack-segmentation
Copyright (c) 2023 Yakhyokhuja Valikhujaev, MIT License.
"""

from typing import Optional

import torch
import torch.nn as nn


def auto_pad(kernel_size: int, dilation: int) -> int:
    return (kernel_size - 1) // 2 * dilation


class Conv(nn.Module):
    def __init__(
        self,
        in_channels: int,
        out_channels: int,
        kernel_size: int = 1,
        stride: int = 1,
        padding: Optional[int] = None,
        groups: int = 1,
        dilation: int = 1,
        bias: bool = False,
        act: bool = True,
    ) -> None:
        super().__init__()
        self.conv = nn.Conv2d(
            in_channels,
            out_channels,
            kernel_size,
            stride,
            auto_pad(kernel_size, dilation) if padding is None else padding,
            dilation,
            groups,
            bias,
        )
        self.bn = nn.BatchNorm2d(out_channels)
        self.act = nn.ReLU(inplace=True) if act else nn.Identity()

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.act(self.bn(self.conv(x)))


class DoubleConv(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, mid_channels: Optional[int] = None) -> None:
        super().__init__()
        mid_channels = mid_channels or out_channels
        self.conv1 = Conv(in_channels, mid_channels, kernel_size=3, padding=1)
        self.conv2 = Conv(mid_channels, out_channels, kernel_size=3, padding=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv2(self.conv1(x))


class Down(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, scale_factor: int = 2) -> None:
        super().__init__()
        self.pool = nn.MaxPool2d(scale_factor)
        self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.conv(self.pool(x))


class Up(nn.Module):
    def __init__(self, in_channels: int, out_channels: int, scale_factor: int = 2) -> None:
        super().__init__()
        self.up = nn.ConvTranspose2d(in_channels, in_channels // 2, kernel_size=2, stride=scale_factor)
        self.conv = DoubleConv(in_channels, out_channels)

    def forward(self, x1: torch.Tensor, x2: torch.Tensor) -> torch.Tensor:
        return self.conv(torch.cat([x2, self.up(x1)], dim=1))


class UNet(nn.Module):
    def __init__(self, in_channels: int = 3, out_channels: int = 2) -> None:
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.input_conv = DoubleConv(in_channels, 64)
        self.down1 = Down(64, 128)
        self.down2 = Down(128, 256)
        self.down3 = Down(256, 512)
        self.down4 = Down(512, 1024)
        self.up1 = Up(1024, 512)
        self.up2 = Up(512, 256)
        self.up3 = Up(256, 128)
        self.up4 = Up(128, 64)
        self.output_conv = nn.Conv2d(64, out_channels, kernel_size=1)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        x0 = self.input_conv(x)
        x1 = self.down1(x0)
        x2 = self.down2(x1)
        x3 = self.down3(x2)
        x4 = self.down4(x3)
        x = self.up1(x4, x3)
        x = self.up2(x, x2)
        x = self.up3(x, x1)
        x = self.up4(x, x0)
        return self.output_conv(x)
