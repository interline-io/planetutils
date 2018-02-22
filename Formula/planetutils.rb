# Documentation: https://docs.brew.sh/Formula-Cookbook.html
#                http://www.rubydoc.info/github/Homebrew/brew/master/Formula
# PLEASE REMOVE ALL GENERATED COMMENTS BEFORE SUBMITTING YOUR PULL REQUEST!
class Planetutils < Formula
  include Language::Python::Virtualenv

  desc "Scripts to maintain your own OpenStreetMap planet"
  homepage "https://github.com/interline-io/planetutils"
  head "https://github.com/interline-io/planetutils.git",
      # :tag => "v0.1.3"
      :branch => 'packaging-and-documentation'
  sha256 "20fd701063e84c74164c8d9f7d31f61f76df94f8"

  depends_on "osmctools"
  depends_on "osmosis"
  depends_on "python" if MacOS.version <= :snow_leopard # we need Python 2.7

  ###
  # Python packages required for boto3
  # generated using https://github.com/tdsmith/homebrew-pypi-poet
  ###
  resource "boto3" do
    url "https://files.pythonhosted.org/packages/03/ae/d901d36291222b097771a03e42e6e2d9c55a70f8808dedc6fc5ff5af96f9/boto3-1.5.33.tar.gz"
    sha256 "239717ef87f1a073a73000af32bbc6828f50063514d934028bd8dc566c2837a6"
  end

  resource "botocore" do
    url "https://files.pythonhosted.org/packages/30/5f/499d676f1048b627ac594a2513acb01d5b32a426a2f474fb6ba95a50c3b3/botocore-1.8.47.tar.gz"
    sha256 "3def0a1ced4cb77624454d77988f64642fd365001fbcedf2c809ce72ec73a406"
  end

  resource "docutils" do
    url "https://files.pythonhosted.org/packages/84/f4/5771e41fdf52aabebbadecc9381d11dea0fa34e4759b4071244fa094804c/docutils-0.14.tar.gz"
    sha256 "51e64ef2ebfb29cae1faa133b3710143496eca21c530f3f71424d77687764274"
  end

  resource "futures" do
    url "https://files.pythonhosted.org/packages/1f/9e/7b2ff7e965fc654592269f2906ade1c7d705f1bf25b7d469fa153f7d19eb/futures-3.2.0.tar.gz"
    sha256 "9ec02aa7d674acb8618afb127e27fde7fc68994c0437ad759fa094a574adb265"
  end

  resource "jmespath" do
    url "https://files.pythonhosted.org/packages/e5/21/795b7549397735e911b032f255cff5fb0de58f96da794274660bca4f58ef/jmespath-0.9.3.tar.gz"
    sha256 "6a81d4c9aa62caf061cb517b4d9ad1dd300374cd4706997aff9cd6aedd61fc64"
  end

  resource "python-dateutil" do
    url "https://files.pythonhosted.org/packages/54/bb/f1db86504f7a49e1d9b9301531181b00a1c7325dc85a29160ee3eaa73a54/python-dateutil-2.6.1.tar.gz"
    sha256 "891c38b2a02f5bb1be3e4793866c8df49c7d19baabf9c1bad62547e0b4866aca"
  end

  resource "s3transfer" do
    url "https://files.pythonhosted.org/packages/9a/66/c6a5ae4dbbaf253bd662921b805e4972451a6d214d0dc9fb3300cb642320/s3transfer-0.1.13.tar.gz"
    sha256 "90dc18e028989c609146e241ea153250be451e05ecc0c2832565231dacdf59c1"
  end

  resource "six" do
    url "https://files.pythonhosted.org/packages/16/d8/bc6316cf98419719bd59c91742194c111b6f2e85abac88e496adefaf7afe/six-1.11.0.tar.gz"
    sha256 "70e8a77beed4562e7f14fe23a786b54f6296e34344c23bc42f07b15018ff98e9"
  end

  def install
    # Create a virtualenv in `libexec`. If your app needs Python 3, make sure that
    # `depends_on "python3"` is declared, and use `virtualenv_create(libexec, "python3")`.
    venv = virtualenv_create(libexec)
    # Install all of the resources declared on the formula into the virtualenv.
    venv.pip_install resources
    # `pip_install_and_link` takes a look at the virtualenv's bin directory
    # before and after installing its argument. New scripts will be symlinked
    # into `bin`. `pip_install_and_link buildpath` will install the package
    # that the formula points to, because buildpath is the location where the
    # formula's tarball was unpacked.
    venv.pip_install_and_link buildpath
  end

  test do
    # TODO: verify a command can work, like:
    # output = shell_output("#{bin}/valhalla_service", 1)
    # assert_match "Usage: #{bin}/valhalla_service config/file.json", output
    system "true"
end
end
