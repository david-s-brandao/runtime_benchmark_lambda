build:
	cargo lambda build --release

zip:
	cp target/lambda/bootstrap/bootstrap .
	zip bootstrap.zip bootstrap
	rm bootstrap

deploy: build zip
