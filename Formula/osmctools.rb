 class Osmctools < Formula
  desc "This project contains a few simple tools which are used in OpenStreetMap project. All programs of this project are written in C."
  homepage "https://gitlab.com/osm-c-tools/osmctools/blob/master/README.md"
  url "https://gitlab.com/osm-c-tools/osmctools.git",
      :tag => "0.8"
  sha256 "69715f3afcfbde5318e853f00af5cd722adadcd24abe26106a121a260c1e7cb3"
   depends_on "automake" => :build
   depends_on "autoconf" => :build
   def install
    system "autoreconf --install"
    system "./configure", "--disable-debug",
                          "--disable-dependency-tracking",
                          "--disable-silent-rules",
                          "--prefix=#{prefix}"
    system "make", "install"
  end
   test do
    # TODO: verify a command can work, like:
    # output = shell_output("#{bin}/valhalla_service", 1)
    # assert_match "Usage: #{bin}/valhalla_service config/file.json", output
    system "true"
  end
end
