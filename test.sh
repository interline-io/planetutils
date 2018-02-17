docker run --rm -v $HOME/data/planets:/data -e AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID} -e AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY} -it osm-planet-update "$@"

