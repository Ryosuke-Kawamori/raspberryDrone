// ============================================================
//  基板ブリッジマウント v5  for BetaFPV Meteor85
//  デフォルトは Raspberry Pi Zero 2 W。Pico W なら [基板] の値を戻すだけ
//
//  OpenSCAD で F5 → F6 → Export as STL
//  ★ = 実測して書き換えるところ
//  印刷向き: 天板を下にしてベッドに置く → サポート不要
// ============================================================

$fn = 40;

/* [基板] */
board       = "zero2w";   // "zero2w" / "picow" / "custom"
//   custom のときは下の値を直接編集
board_l_c   = 65.0;
board_w_c   = 30.0;
hole_dx_c   = 58.0;
hole_dy_c   = 23.0;
hole_pilot_c=  2.2;      // タッピング下穴 (M2.5→2.2 / M2→1.7)

board_fix   = "screw";   // "screw" = スタンドオフにタッピング / "ziptie" = 結束バンド
standoff_h  =  3.0;      // 基板裏のクリアランス
standoff_d  =  5.5;

/* [機体側 実測値] */
canopy_h    = 40.0;   // ★ フレーム上面 → キャノピー最頂部
tab_h       =  0.0;   // ★ キャノピー固定タブの上面高さ(フレーム上面から)
clearance   =  1.0;   // ★ 基板が重いので低め推奨。当たるなら上げる
screw_span  = 50.0;   // ★ 左右ネジ穴の中心間距離
screw_d     =  1.7;   // ★ ネジ軸径の実測 + 0.3
screw_head_d=  3.4;   // ★ ネジ頭の外径
screw_head  = "pan";  // "pan" / "flat"(皿)
screw_len   =  0.0;   // ★ 今のネジの全長(0なら判定しない)
flat_y      = 30.0;   // ★ 足が載る平面の前後幅
nozzle_d    =  0.4;   // ★ ノズル径

/* [天板] */
plate_t     =  1.2;
plate_margin=  2.0;   // 基板外形に対する天板の余白
fillet      =  2.5;

/* [脚] */
leg_web_t   =  1.8;
leg_web_w   = 11.0;
leg_spine_l =  5.2;
leg_spine_t =  1.8;
leg_top_z   = 14.0;   // ここから下は2本柱

/* [ハンチ] */
haunch_h    =  4.5;
haunch_hx   =  2.5;
haunch_hy   =  8.5;

/* [足まわり] */
post_t      =  2.8;   // 柱 横(左右X)
post_w      =  3.0;   // 柱 縦(前後Y)
post_y      =  7.0;   // ★ 柱の中心オフセット → 隙間 = 2*(post_y - post_w/2)
foot_hx     =  3.8;   // 足パッド 左右 半幅
foot_hy     =  8.8;   // 足パッド 前後 半幅 (>= post_y + post_w/2)
foot_t      =  1.4;
foot_taper_h=  3.0;

/* [オプション] */
lighten     = true;
cable_slot  = true;
show_dummy  = false;

// ---------------- 基板プリセット ----------------
board_l  = board=="zero2w" ? 65.0 : board=="picow" ? 51.0 : board_l_c;
board_w  = board=="zero2w" ? 30.0 : board=="picow" ? 21.0 : board_w_c;
hole_dx  = board=="zero2w" ? 58.0 : board=="picow" ? 47.0 : hole_dx_c;
hole_dy  = board=="zero2w" ? 23.0 : board=="picow" ? 11.4 : hole_dy_c;
hole_pil = board=="zero2w" ?  2.2 : board=="picow" ?  1.7 : hole_pilot_c;

// ---------------- 派生値 ----------------
deck     = canopy_h + clearance - tab_h;
top      = deck + plate_t;
xc       = screw_span / 2;
plate_hx = board_l/2 + plate_margin;
plate_hy = board_w/2 + plate_margin;
driver_gap   = 2*(post_y - post_w/2);
head_clear_y = 2*(post_y - (post_w+0.6)/2);
foot_ang     = atan((foot_hx - post_t/2) / foot_taper_h);

echo(str(">> 基板 ", board, " ", board_l, "x", board_w, " 穴 ", hole_dx, "x", hole_dy));
echo(str(">> 天板 = ", 2*plate_hx, " x ", 2*plate_hy, " / 天板裏 z = ", deck, " / 全高 = ", top + (board_fix=="screw" ? standoff_h : 0)));
echo(str(">> 柱 = ", post_t, " x ", post_w, " / 隙間 = ", driver_gap, " / 足パッド = ", 2*foot_hx, " x ", 2*foot_hy, " / テーパー ", foot_ang, " deg"));
echo(str(">> ネジは今より ", foot_t, " mm 長いものが必要"));
if (screw_len > 0) echo(str(">> 用意すべきネジ全長 = ", screw_len + foot_t, " mm 以上"));
if (driver_gap < 4)               echo("!! 隙間が狭くネジを締められない。post_y を上げる");
if (screw_head_d + 1.5 > driver_gap) echo("!! ネジ頭が柱の隙間を通らない。post_y を上げる");
if (screw_head_d + 1.0 > head_clear_y) echo("!! テーパーがネジ頭に当たる。post_y を上げる");
if (foot_hy < post_y + post_w/2 + 0.3) echo("!! 足パッドが柱より狭い。foot_hy を上げる");
if (2*foot_hy > flat_y)           echo("!! 足パッドが平面からはみ出す");
if (foot_ang > 45)                echo("!! 足のテーパーが寝すぎ。foot_hx を下げるか foot_taper_h を上げる");
if (foot_hx < screw_head_d/2 + 1.0) echo("!! 足パッドが狭くネジ頭が収まらない。foot_hx を上げる");
if (min(post_t, post_w) < nozzle_d*4 + 0.3) echo("!! 柱が細すぎる。post_t / post_w を上げる");
if (xc + haunch_hx > plate_hx)    echo("!! ハンチが天板からはみ出す。haunch_hx を下げる");
if (screw_head=="flat" && foot_t < (screw_head_d-screw_d)/2 + 0.6) echo("!! 皿ネジで足パッドが薄すぎ。foot_t を上げる");
if (hole_dx/2 + standoff_d/2 > plate_hx || hole_dy/2 + standoff_d/2 > plate_hy)
    echo("!! スタンドオフが天板からはみ出す。plate_margin を上げる");
if (tab_h == 0) echo("-- tab_h が 0。タブ高さを入れると天板高さが正確になる");

// ============================================================
module rbox(x, y, z, r=1.0) {
    hull() for (i=[-1,1], j=[-1,1])
        translate([i*(x/2-r), j*(y/2-r), 0]) cylinder(r=r, h=z);
}

module solid() {
    translate([0,0,deck]) rbox(2*plate_hx, 2*plate_hy, plate_t, fillet);

    if (board_fix == "screw")
        for (i=[-1,1], j=[-1,1])
            translate([i*hole_dx/2, j*hole_dy/2, top-0.01])
                cylinder(d=standoff_d, h=standoff_h+0.01);

    for (s = [-1,1]) {
        translate([s*xc, 0, 0]) hull() {
            translate([0,0,deck-0.01]) rbox(2*haunch_hx, 2*haunch_hy, 0.01, 1.2);
            translate([0,0,deck-haunch_h]) rbox(leg_spine_l, leg_web_w, 0.01, 0.8);
        }
        translate([s*xc, 0, leg_top_z]) {
            rbox(leg_web_t,   leg_web_w,   deck-leg_top_z, 0.6);
            rbox(leg_spine_l, leg_spine_t, deck-leg_top_z, 0.6);
        }
        for (sy = [-1,1])
            translate([s*xc, sy*post_y, foot_t + foot_taper_h])
                rbox(post_t, post_w, leg_top_z + 1.5 - foot_t - foot_taper_h, 0.6);
        translate([s*xc, 0, 0]) hull() {
            translate([0,0,leg_top_z+1.5-0.01]) rbox(leg_web_t, leg_web_w, 0.01, 0.6);
            translate([0,0,leg_top_z-2.5])      rbox(leg_web_t, 2*post_y+post_w, 0.01, 0.6);
        }
        translate([s*xc, 0, 0]) {
            rbox(2*foot_hx, 2*foot_hy, foot_t, 1.2);
            for (sy = [-1,1])
                translate([0, sy*post_y, 0]) hull() {
                    translate([0,0,foot_t-0.01])        rbox(2*foot_hx, post_w+0.6, 0.01, 0.8);
                    translate([0,0,foot_t+foot_taper_h]) rbox(post_t, post_w, 0.01, 0.6);
                }
        }
    }
}

module cuts() {
    cs = (screw_head_d - screw_d)/2;
    for (s = [-1,1]) translate([s*xc, 0, 0]) {
        translate([0,0,-1]) cylinder(d=screw_d, h=foot_t+2);
        if (screw_head == "flat")
            translate([0,0,foot_t-cs]) cylinder(d1=screw_d, d2=screw_head_d, h=cs+0.01);
    }

    if (board_fix == "screw")
        for (i=[-1,1], j=[-1,1])
            translate([i*hole_dx/2, j*hole_dy/2, deck-1])
                cylinder(d=hole_pil, h=plate_t+standoff_h+2);

    if (board_fix == "ziptie")
        for (sx=[-1,1], sy=[-1,1])
            translate([sx*(board_l/2-10), sy*(board_w/2+0.1), deck+plate_t/2])
                cube([3.4, 1.8, plate_t+2], center=true);

    if (cable_slot)
        translate([0, plate_hy-1.9, deck+plate_t/2]) cube([8, 8, plate_t+2], center=true);

    if (lighten) {
        n  = floor((plate_hx - 6) / 7.5);
        wy = 2*plate_hy - 9;
        for (k = [-n:n])
            translate([k*7.5, 0, deck+plate_t/2]) rbox(5.8, wy, plate_t+2, 1.6);
    }
}

difference() { solid(); cuts(); }

if (show_dummy) {
    zb = top + (board_fix=="screw" ? standoff_h : 0) + 0.5;
    %translate([0,0,zb]) cube([board_l, board_w, 1.4], center=true);
    %translate([0,0,canopy_h/2]) scale([14,18,canopy_h/2]) sphere(1);
}
