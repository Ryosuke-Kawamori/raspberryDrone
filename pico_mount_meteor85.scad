// ============================================================
//  Raspberry Pi Pico W  ブリッジマウント  v4
//  for BetaFPV Meteor85
//
//  OpenSCAD で開いて F5 プレビュー → F6 → Export as STL
//  ★ = 実測して書き換えるところ
//  印刷向き: 天板を下にしてベッドに置く → サポート不要
// ============================================================

$fn = 40;

/* [機体側 実測値] */
canopy_h    = 40.0;   // ★ フレーム上面 → キャノピー最頂部
clearance   =  2.5;   // ★ キャノピー天面と天板裏のすき間
screw_span  = 50.0;   // ★ 左右ネジ穴の中心間距離
screw_d     =  1.7;   // ★ ネジ軸径の実測 + 0.3
tab_h       =  0.0;   // ★ キャノピー固定タブの上面高さ(フレーム上面から)
                      //    足パッドはこのタブの上に載るので、その分 脚を短くする
screw_len   =  0.0;   // ★ 今使っているネジの全長(0なら判定しない)
screw_head_d=  3.4;   // ★ ネジ頭の外径 実測
screw_head  = "pan";  // ★ "pan"=なべ/トラス頭 そのまま / "flat"=皿ネジ用テーパー
flat_y      = 30.0;   // ★ 足が載る平面の前後幅(天板幅の上限判定に使う)

/* [Pico W  公称値・変更不要] */
pico_l      = 51.0;
pico_w      = 21.0;

/* [天板] */
plate_t     =  1.2;
plate_margin=  2.0;   // ★ Pico外形に対する天板の余白(左右)。負にもできる
plate_hy    = 12.0;   // 天板の前後 半幅
fillet      =  2.5;

/* [脚] */
leg_web_t   =  1.8;   // 脚 主ウェブ厚(左右方向)
leg_web_w   = 11.0;   // 脚 主ウェブ幅(前後方向)
leg_spine_l =  5.2;   // 脚 背骨の長さ(左右方向)
leg_spine_t =  1.8;   // 脚 背骨の厚み
leg_top_z   = 14.0;   // 脚(1本部分)の下端高さ = ここから下は2本に分岐

/* [ハンチ = 天板との付け根の斜面] */
haunch_h    =  4.5;
haunch_hx   =  2.5;   // 左右幅を詰めたので小さく
haunch_hy   =  8.5;   // その分 前後で稼ぐ

/* [足まわり] */
post_t      =  2.8;   // 分岐した柱の厚み(左右)
post_w      =  3.0;   // 分岐した柱の幅(前後)
post_y      =  7.0;   // ★ 柱の中心 前後オフセット → 隙間 = 2*(post_y - post_w/2)
foot_hx     =  3.8;
foot_hy     =  8.8;
foot_t      =  1.4;
foot_taper_h=  3.0;   // 足パッド→柱 のテーパー高さ(印刷のオーバーハング対策)

/* [オプション] */
lighten     = true;
cable_slot  = true;
show_dummy  = false;  // true にすると Pico とキャノピーの当たりを半透明表示

// ---------------- 派生値 ----------------
deck     = canopy_h + clearance - tab_h;  // 天板 裏面高さ(足パッド底面からの高さ)
top      = deck + plate_t;
xc       = screw_span / 2;
plate_hx = pico_l/2 + plate_margin;
driver_gap = 2*(post_y - post_w/2);

echo(str(">> 天板裏 z = ", deck, " / 全高 = ", top, " mm"));
echo(str(">> 天板 = ", 2*plate_hx, " x ", 2*plate_hy, " mm"));
echo(str(">> 足パッド 前後 = ", 2*foot_hy, " mm / 天板が左右に出る量 = ", plate_hx - xc, " mm"));
echo(str(">> ドライバー隙間 = ", driver_gap, " mm"));
echo(str(">> ネジは今より ", foot_t, " mm 長いものが必要"));
if (screw_len > 0)
    echo(str(">> 用意すべきネジ全長 = ", screw_len + foot_t, " mm 以上"));
if (driver_gap < 4)
    echo("!! 警告: 隙間が狭くネジを締められません。post_y を大きく");
if (2*plate_hy > flat_y)
    echo("!! 警告: 天板がダクト間の平面より広い。plate_hy を下げる");
if (xc + haunch_hx > plate_hx)
    echo("!! 警告: ハンチが天板からはみ出す。haunch_hx を下げる");
if (foot_hy < post_y + post_w/2 + 0.4)
    echo("!! 警告: 足パッドが柱より狭い。foot_hy を上げる");
if (2*foot_hy > flat_y)
    echo("!! 警告: 足パッドが平面からはみ出す");
if (screw_head == "flat" && foot_t < (screw_head_d-screw_d)/2 + 0.6)
    echo("!! 警告: 皿ネジのテーパーで足パッドが薄くなりすぎ。foot_t を上げる");
if (screw_head_d + 1.5 > driver_gap)
    echo("!! 警告: ネジ頭が柱の隙間を通らない。post_y を上げる");
if (screw_head_d/2 + 1.2 > foot_hx)
    echo("!! 警告: ネジ頭が足パッド(左右)からはみ出す。foot_hx を上げる");
head_clear_y = 2*(post_y - (post_w+0.6)/2);
echo(str(">> ネジ頭まわりの前後クリア = ", head_clear_y, " mm"));
if (screw_head_d + 1.0 > head_clear_y)
    echo("!! 警告: テーパーがネジ頭に当たる。post_y を上げる");
if (tab_h == 0)
    echo("-- tab_h が 0 です。タブの高さを実測して入れると天板高さが正確になります");

// ============================================================
module rbox(x, y, z, r=1.0) {
    hull() for (i=[-1,1], j=[-1,1])
        translate([i*(x/2-r), j*(y/2-r), 0]) cylinder(r=r, h=z);
}
module slab(x, y, z0, z1) {         // 中心 XY・z範囲指定の板
    translate([0,0,z0]) cube([x, y, z1-z0], center=false);
}

// ============================================================
module solid() {
    // ---- 天板 ----
    translate([0,0,deck]) rbox(2*plate_hx, 2*plate_hy, plate_t, fillet);

    for (s = [-1,1]) {
        // ---- ハンチ(本物の斜面) ----
        translate([s*xc, 0, 0])
            hull() {
                translate([0,0,deck-0.01])
                    rbox(2*haunch_hx, 2*haunch_hy, 0.01, 1.2);
                translate([0,0,deck-haunch_h])
                    rbox(leg_spine_l, leg_web_w, 0.01, 0.8);
            }
        // ---- 脚(十字断面) ----
        translate([s*xc, 0, leg_top_z]) {
            rbox(leg_web_t,  leg_web_w,  deck-leg_top_z, 0.6);
            rbox(leg_spine_l, leg_spine_t, deck-leg_top_z, 0.6);
        }
        // ---- 分岐した2本の柱 ----
        for (sy = [-1,1])
            translate([s*xc, sy*post_y, foot_t + foot_taper_h])
                rbox(post_t, post_w, leg_top_z + 1.5 - foot_t - foot_taper_h, 0.6);
        // ---- 柱→脚 の合流部(テーパー) ----
        translate([s*xc, 0, 0])
            hull() {
                translate([0,0,leg_top_z+1.5-0.01])
                    rbox(leg_web_t, leg_web_w, 0.01, 0.6);
                translate([0,0,leg_top_z-2.5])
                    rbox(leg_web_t, 2*post_y+post_w, 0.01, 0.6);
            }
        // ---- 足パッド ----
        //  中央(y=0)はネジ頭とドライバーのため開けたままにする
        translate([s*xc, 0, 0]) {
            rbox(2*foot_hx, 2*foot_hy, foot_t, 1.2);
            for (sy = [-1,1])
                translate([0, sy*post_y, 0]) hull() {
                    translate([0,0,foot_t-0.01])
                        rbox(2*foot_hx, post_w+0.6, 0.01, 0.8);
                    translate([0,0,foot_t+foot_taper_h])
                        rbox(post_t, post_w, 0.01, 0.6);
                }
        }
    }
}

module cuts() {
    // ---- ネジ貫通穴(足パッド中央 x=±screw_span/2) ----
    cs = (screw_head_d - screw_d)/2;      // 皿ネジのテーパー深さ(90deg)
    for (s = [-1,1]) translate([s*xc, 0, 0]) {
        translate([0,0,-1]) cylinder(d=screw_d, h=foot_t+2);
        if (screw_head == "flat")
            translate([0,0,foot_t-cs])
                cylinder(d1=screw_d, d2=screw_head_d, h=cs+0.01);
    }

    // ---- 結束バンド用スロット(Pico を天板に留める) ----
    for (sx = [-1,1], sy = [-1,1])
        translate([sx*15, sy*(pico_w/2 + 0.1), deck + plate_t/2])
            cube([3.4, 1.8, plate_t+2], center=true);

    // ---- FCへの配線スリット(後端に開口) ----
    if (cable_slot)
        translate([0, plate_hy - 1.9, deck + plate_t/2])
            cube([8, 8, plate_t+2], center=true);

    // ---- 肉抜き窓 ----
    if (lighten)
        for (cx = [-18.5,-11,-3.5,3.5,11,18.5])
            translate([cx, 0, deck + plate_t/2])
                rbox(5.8, 15.2, plate_t+2, 1.6);
}

difference() { solid(); cuts(); }

// ============================================================
if (show_dummy) {
    %translate([0,0,top+0.5]) cube([pico_l, pico_w, 1.0], center=true);
    %translate([0,0,canopy_h/2]) scale([14,18,canopy_h/2]) sphere(1);
}
